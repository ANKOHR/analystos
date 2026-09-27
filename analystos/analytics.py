"""Calculations and traceable evidence records for the management report."""

from __future__ import annotations

from collections import Counter
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

from analystos.io_utils import write_json
from analystos.qa import resolve_raw_dir


def _rounded(value: float, digits: int = 2) -> float:
    return round(float(value) + 1e-10, digits)


def analyze(cleaned_path: Path, raw_data_dir: Path, cleaning: dict[str, Any], qa: dict[str, Any], out_dir: Path) -> dict[str, Any]:
    raw_dir = resolve_raw_dir(raw_data_dir)
    sales = pd.read_csv(cleaned_path)
    customers = pd.read_csv(raw_dir / "customers.csv")
    products = pd.read_csv(raw_dir / "products.csv")
    raw_sales = pd.read_csv(raw_dir / "sales.csv")

    sales["sale_date"] = pd.to_datetime(sales["sale_date"], format="%Y-%m-%d")
    sales["month"] = sales["sale_date"].dt.to_period("M").astype(str)
    sales["revenue"] = sales["revenue"].astype(float)
    sales["quantity"] = sales["quantity"].astype(int)
    total_revenue = _rounded(sales["revenue"].sum())
    monthly = sales.groupby("month", sort=True)["revenue"].sum().round(2)
    monthly_frame = [{"month": str(month), "revenue": _rounded(value)} for month, value in monthly.items()]

    first_months = list(monthly.index[:3])
    last_months = list(monthly.index[-3:])
    first_total = _rounded(float(monthly.iloc[:3].sum()))
    last_total = _rounded(float(monthly.iloc[-3:].sum()))
    growth_pct = _rounded((last_total / first_total - 1.0) * 100.0 if first_total else 0.0)

    customer_count = int(sales["customer_id"].nunique())
    customer_purchase_counts = sales.groupby("customer_id")["sale_id"].nunique()
    repeat_count = int((customer_purchase_counts > 1).sum())
    repeat_pct = _rounded(repeat_count / customer_count * 100.0 if customer_count else 0.0)

    product_revenue = (
        sales.merge(products[["product_id", "category"]], on="product_id", how="left")
        .groupby("category", sort=True)["revenue"]
        .sum()
        .sort_values(ascending=False, kind="stable")
    )
    product_total = float(product_revenue.sum())
    product_mix = [
        {
            "category": str(category),
            "revenue": _rounded(value),
            "share_pct": _rounded(value / product_total * 100.0 if product_total else 0.0),
        }
        for category, value in product_revenue.items()
    ]
    leading_category = product_mix[0] if product_mix else {"category": "Unknown", "revenue": 0.0, "share_pct": 0.0}

    sales["cohort_month"] = sales.groupby("customer_id")["month"].transform("min")
    cohort_counts = (
        sales.groupby(["cohort_month", "month"], sort=True)["customer_id"]
        .nunique()
        .rename("customers")
        .reset_index()
    )
    cohort_counts["cohort_period"] = (
        (cohort_counts["month"].str[:4].astype(int) - cohort_counts["cohort_month"].str[:4].astype(int)) * 12
        + cohort_counts["month"].str[5:7].astype(int)
        - cohort_counts["cohort_month"].str[5:7].astype(int)
    )
    cohort_sizes = cohort_counts.groupby("cohort_month")["customers"].first()
    cohort_counts["retention_pct"] = cohort_counts.apply(
        lambda row: _rounded(row["customers"] / cohort_sizes.loc[row["cohort_month"]] * 100.0), axis=1
    )
    cohort_table = cohort_counts.pivot(index="cohort_month", columns="cohort_period", values="retention_pct")
    cohort_table = cohort_table.sort_index().sort_index(axis=1)
    cohort_data = {
        "cohorts": [str(value) for value in cohort_table.index],
        "periods": [int(value) for value in cohort_table.columns],
        "retention_pct": [
            [None if pd.isna(value) else _rounded(value) for value in row]
            for row in cohort_table.to_numpy(dtype=object).tolist()
        ],
    }

    review = pd.read_csv(cleaning["review_path"])
    review_reasons = dict(sorted(Counter(review["reason"].astype(str)).items())) if len(review) else {}
    missing_repaired = sum(
        1 for event in cleaning["audit_events_data"] if event["field"] != "__row__" and event["old_value"] == ""
    )
    break_rows = qa["checks"]["reconciliation_breaks"]["periods"]
    outlier_count = int(qa["checks"]["outliers"]["count"])
    variant_count = int(qa["checks"]["label_variants"]["count"])
    duplicate_count = int(qa["checks"]["duplicate_rows"]["count"])
    break_count = len(break_rows)
    source_dates = dict(zip(raw_sales["source_row"].astype(str), raw_sales["sale_date"].astype(str)))
    event_months = [
        source_dates[event["row_id"]][:7]
        for event in cleaning["audit_events_data"]
        if event["field"] != "__row__" and event["row_id"] in source_dates
    ]
    event_month_counts = dict(sorted(Counter(event_months).items()))

    calculations = [
        {
            "id": "CALC-001",
            "name": "Cleaned transaction revenue",
            "formula": "sum(cleaned sales revenue)",
            "source": "cleaned/sales_clean.csv, revenue column",
            "result": {"currency": "USD synthetic units", "value": total_revenue, "transaction_rows": int(len(sales))},
        },
        {
            "id": "CALC-002",
            "name": "Revenue change across edge windows",
            "formula": "(last three monthly totals / first three monthly totals - 1) * 100",
            "source": "cleaned/sales_clean.csv grouped by calendar month",
            "parameters": {"first_months": first_months, "last_months": last_months},
            "result": {
                "first_months": first_months,
                "last_months": last_months,
                "first_window_revenue": first_total,
                "last_window_revenue": last_total,
                "change_pct": growth_pct,
            },
        },
        {
            "id": "CALC-003",
            "name": "Distinct purchasing customers",
            "formula": "nunique(customer_id) in cleaned sales",
            "source": "cleaned/sales_clean.csv, customer_id column",
            "result": {"customer_count": customer_count},
        },
        {
            "id": "CALC-004",
            "name": "Repeat purchasing customers",
            "formula": "customers with more than one distinct sale_id / distinct purchasing customers * 100",
            "source": "cleaned/sales_clean.csv grouped by customer_id",
            "result": {"repeat_customer_count": repeat_count, "customer_count": customer_count, "repeat_customer_pct": repeat_pct},
        },
        {
            "id": "CALC-005",
            "name": "Revenue by product category",
            "formula": "sum(cleaned sales revenue) grouped by products.category",
            "source": "cleaned/sales_clean.csv joined to raw/products.csv",
            "result": {"categories": product_mix, "leading_category": leading_category},
        },
        {
            "id": "CALC-006",
            "name": "Rows retained in the review queue",
            "formula": "count(rows in cleaned/review_queue.csv)",
            "source": "cleaned/review_queue.csv",
            "result": {"row_count": int(len(review)), "reasons": review_reasons},
        },
        {
            "id": "CALC-007",
            "name": "Monthly rollup reconciliation",
            "formula": "count(months where monthly reported revenue differs from sum of daily reported revenue by at least 0.01)",
            "source": "raw/daily_rollups.csv and raw/monthly_rollups.csv",
            "result": {"break_count": break_count, "periods": break_rows},
        },
        {
            "id": "CALC-008",
            "name": "QA exception counts",
            "formula": "counts computed from source sales and rollup CSV files during QA",
            "source": "qa/qa_report.json",
            "result": {
                "outlier_rows": outlier_count,
                "duplicate_rows": duplicate_count,
                "label_variant_groups": variant_count,
                "missing_cells": int(qa["checks"]["missing_values"]["count"]),
                "missing_cells_repaired": missing_repaired,
            },
        },
        {
            "id": "CALC-009",
            "name": "Customer cohort retention",
            "formula": "distinct active customers in each cohort month / distinct customers in the cohort's first month * 100",
            "source": "cleaned/sales_clean.csv grouped by first purchase month and purchase month",
            "result": cohort_data,
        },
        {
            "id": "CALC-010",
            "name": "Cleaning events by transaction month",
            "formula": "count field-level audit events by source transaction month, excluding row-level quarantine events",
            "source": "cleaned/cleaning_audit.csv joined to raw/sales.csv by source_row",
            "result": {"total_field_events": len(event_months), "events_by_month": event_month_counts},
        },
    ]

    claims = [
        {
            "id": "C-001",
            "kind": "calculation",
            "text": "Cleaned transaction revenue total",
            "value": total_revenue,
            "display_value": f"${total_revenue:,.2f}",
            "unit": "USD synthetic units",
            "evidence_pointer": "CALC-001",
        },
        {
            "id": "C-002",
            "kind": "calculation",
            "text": "Revenue change between the first and last three monthly windows",
            "value": growth_pct,
            "display_value": f"{growth_pct:,.2f}%",
            "unit": "percent",
            "evidence_pointer": "CALC-002",
        },
        {
            "id": "C-003",
            "kind": "calculation",
            "text": "Distinct purchasing customer count",
            "value": customer_count,
            "display_value": f"{customer_count:,}",
            "unit": "customers",
            "evidence_pointer": "CALC-003",
        },
        {
            "id": "C-004",
            "kind": "calculation",
            "text": "Repeat purchasing customer share",
            "value": repeat_pct,
            "display_value": f"{repeat_pct:,.2f}%",
            "unit": "percent",
            "evidence_pointer": "CALC-004",
        },
        {
            "id": "C-005",
            "kind": "calculation",
            "text": "Largest product category by cleaned revenue",
            "value": leading_category,
            "display_value": f"{leading_category['category']} at {leading_category['share_pct']:,.2f}%",
            "unit": "category and percent",
            "evidence_pointer": "CALC-005",
        },
        {
            "id": "C-006",
            "kind": "calculation",
            "text": "Rows retained in the review queue",
            "value": int(len(review)),
            "display_value": f"{len(review):,}",
            "unit": "rows",
            "evidence_pointer": "CALC-006",
        },
        {
            "id": "C-007",
            "kind": "calculation",
            "text": "Monthly rollup reconciliation breaks",
            "value": break_count,
            "display_value": f"{break_count:,}",
            "unit": "months",
            "evidence_pointer": "CALC-007",
        },
        {
            "id": "C-008",
            "kind": "calculation",
            "text": "Revenue outlier rows flagged by QA",
            "value": outlier_count,
            "display_value": f"{outlier_count:,}",
            "unit": "rows",
            "evidence_pointer": "CALC-008",
        },
        {
            "id": "C-009",
            "kind": "calculation",
            "text": "Customer cohort retention values plotted in the cohort chart",
            "value": cohort_data,
            "display_value": "Customer retention by first purchase month",
            "unit": "percent by cohort month",
            "evidence_pointer": "CALC-009",
        },
        {
            "id": "C-010",
            "kind": "calculation",
            "text": "Field-level cleaning events annotated on the revenue chart",
            "value": len(event_months),
            "display_value": f"{len(event_months):,} field-level events",
            "unit": "audit events",
            "evidence_pointer": "CALC-010",
        },
    ]
    assumptions = [
        {
            "id": "A-001",
            "kind": "assumption",
            "text": "A missing unit price can be represented by the matching product list price.",
            "basis": "Deterministic repair rule used for the synthetic transaction with a missing unit price.",
            "evidence_pointer": "CALC-008",
        },
        {
            "id": "A-002",
            "kind": "assumption",
            "text": "Observed associations in these records do not establish a cause for revenue changes.",
            "basis": "The generated dataset contains transactions and rollups, with no causal intervention or verified external context.",
            "evidence_pointer": "CALC-002",
        },
    ]
    hypotheses = [
        {
            "id": "HYP-001",
            "classification": "data-backed candidate",
            "text": "The reported monthly mismatch is localized to the periods listed in the reconciliation calculation.",
            "evidence_pointer": "CALC-007",
            "caveat": "The calculations locate the difference but do not identify its operational cause.",
        },
        {
            "id": "HYP-002",
            "classification": "assumption",
            "text": "The missing unit price may represent an omitted catalog value in the source export.",
            "evidence_pointer": "A-001",
            "caveat": "This explanation is not proven by the generated records.",
        },
    ]
    claims_payload = {"data_origin": "Synthetic data", "claims": claims, "assumptions": assumptions, "hypotheses": hypotheses}

    results = {
        "data_origin": "Synthetic data",
        "monthly_revenue": monthly_frame,
        "product_mix": product_mix,
        "customer_cohorts": cohort_data,
        "cleaning_event_counts_by_month": event_month_counts,
        "calculations": calculations,
        "claims_file": "claims.json",
        "qa_summary": {
            name: int(check["count"])
            for name, check in qa["checks"].items()
        },
    }
    results_path = out_dir / "results.json"
    claims_path = out_dir / "claims.json"
    write_json(results_path, results)
    write_json(claims_path, claims_payload)
    return {"results": results, "claims": claims_payload, "results_path": results_path, "claims_path": claims_path}
