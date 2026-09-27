"""Deterministic repairs, quarantine handling, and field-level audit events."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pandas as pd

from analystos.io_utils import write_csv
from analystos.qa import assess_data, resolve_raw_dir

AUDIT_FIELDS = ["row_id", "sale_id", "field", "old_value", "new_value", "rule"]


def _display(value: Any) -> str:
    if value is None or pd.isna(value):
        return ""
    if isinstance(value, float):
        return f"{value:.2f}"
    return str(value)


def clean_sales(data_dir: Path, out_dir: Path, qa_report: dict[str, Any] | None = None) -> dict[str, Any]:
    raw_dir = resolve_raw_dir(data_dir)
    sales = pd.read_csv(raw_dir / "sales.csv", keep_default_na=True)
    customers = pd.read_csv(raw_dir / "customers.csv")
    products = pd.read_csv(raw_dir / "products.csv")
    qa = qa_report or assess_data(data_dir)
    canonical_names = dict(zip(customers["customer_id"].astype(str), customers["customer_name"].astype(str)))
    list_prices = dict(zip(products["product_id"].astype(str), products["list_price"].astype(float)))
    duplicate_sources = set(qa["checks"]["duplicate_rows"]["source_rows"])
    outlier_sources = set(qa["checks"]["outliers"]["source_rows"])

    cleaned: list[dict[str, Any]] = []
    quarantined: list[dict[str, Any]] = []
    audit: list[dict[str, str]] = []
    for raw in sales.to_dict(orient="records"):
        row = dict(raw)
        source_row = int(row["source_row"])
        row_id = str(source_row)
        sale_id = str(row["sale_id"])

        if pd.isna(row.get("unit_price")) and str(row.get("product_id")) in list_prices:
            old = row.get("unit_price")
            new = list_prices[str(row["product_id"])]
            row["unit_price"] = new
            audit.append(
                {
                    "row_id": row_id,
                    "sale_id": sale_id,
                    "field": "unit_price",
                    "old_value": _display(old),
                    "new_value": _display(new),
                    "rule": "impute_missing_unit_price_from_product_list_price",
                }
            )

        if pd.isna(row.get("revenue")) and not pd.isna(row.get("quantity")) and not pd.isna(row.get("unit_price")):
            old = row.get("revenue")
            new = round(float(row["quantity"]) * float(row["unit_price"]), 2)
            row["revenue"] = new
            audit.append(
                {
                    "row_id": row_id,
                    "sale_id": sale_id,
                    "field": "revenue",
                    "old_value": _display(old),
                    "new_value": _display(new),
                    "rule": "recalculate_missing_revenue_from_quantity_times_unit_price",
                }
            )

        customer_id = str(row.get("customer_id"))
        canonical = canonical_names.get(customer_id)
        if canonical is not None and not pd.isna(row.get("customer_label")) and str(row["customer_label"]) != canonical:
            old = row["customer_label"]
            row["customer_label"] = canonical
            audit.append(
                {
                    "row_id": row_id,
                    "sale_id": sale_id,
                    "field": "customer_label",
                    "old_value": _display(old),
                    "new_value": canonical,
                    "rule": "normalize_customer_label_to_customer_master",
                }
            )

        missing_required = [
            field
            for field in ("sale_date", "customer_id", "product_id", "quantity", "unit_price", "revenue")
            if pd.isna(row.get(field))
        ]
        if source_row in duplicate_sources:
            reason = "duplicate transaction retained for review"
        elif source_row in outlier_sources:
            reason = "revenue outlier retained for review"
        elif missing_required:
            reason = "required values could not be repaired: " + ", ".join(missing_required)
        else:
            cleaned.append(row)
            continue

        review_row = dict(row)
        review_row["reason"] = reason
        quarantined.append(review_row)
        audit.append(
            {
                "row_id": row_id,
                "sale_id": sale_id,
                "field": "__row__",
                "old_value": "included_in_analysis_candidate",
                "new_value": "retained_in_review_queue",
                "rule": "quarantine_with_explicit_reason",
            }
        )

    cleaned_dir = out_dir / "cleaned"
    clean_path = cleaned_dir / "sales_clean.csv"
    review_path = cleaned_dir / "review_queue.csv"
    audit_path = cleaned_dir / "cleaning_audit.csv"
    source_fields = list(sales.columns)
    def stable_rows(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
        formatted = []
        for row in rows:
            output_row = dict(row)
            for field in ("unit_price", "revenue"):
                if not pd.isna(output_row.get(field)):
                    output_row[field] = f"{float(output_row[field]):.2f}"
            formatted.append(output_row)
        return formatted

    write_csv(clean_path, stable_rows(cleaned), source_fields)
    write_csv(review_path, stable_rows(quarantined), ["reason", *source_fields])
    write_csv(audit_path, audit, AUDIT_FIELDS)
    return {
        "data_origin": "Synthetic data",
        "cleaned_path": clean_path,
        "review_path": review_path,
        "audit_path": audit_path,
        "cleaned_rows": len(cleaned),
        "quarantined_rows": len(quarantined),
        "audit_events": len(audit),
        "audit_events_data": audit,
    }
