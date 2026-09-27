"""Deterministic data-quality checks for generated CSV inputs."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

from analystos.io_utils import write_json


def resolve_raw_dir(data_dir: Path) -> Path:
    candidate = data_dir / "raw"
    return candidate if candidate.is_dir() else data_dir


def assess_data(data_dir: Path) -> dict[str, Any]:
    raw_dir = resolve_raw_dir(data_dir)
    sales = pd.read_csv(raw_dir / "sales.csv")
    daily = pd.read_csv(raw_dir / "daily_rollups.csv")
    monthly = pd.read_csv(raw_dir / "monthly_rollups.csv")

    missing_fields = {
        str(column): int(count)
        for column, count in sales.isna().sum().items()
        if int(count) > 0
    }
    missing_rows_by_field = {
        str(column): [int(value) for value in sales.loc[sales[column].isna(), "source_row"].tolist()]
        for column in sales.columns
        if sales[column].isna().any()
    }
    compare_columns = [column for column in sales.columns if column not in {"source_row", "data_label"}]
    duplicate_mask = sales.duplicated(subset=compare_columns, keep="first")
    duplicate_sources = [int(value) for value in sales.loc[duplicate_mask, "source_row"].tolist()]

    label_variants = []
    for customer_id, group in sales.groupby("customer_id", dropna=True, sort=True):
        labels = sorted(str(value) for value in group["customer_label"].dropna().unique())
        if len(labels) > 1:
            label_variants.append({"customer_id": str(customer_id), "labels": labels, "variant_count": len(labels)})

    revenue = pd.to_numeric(sales["revenue"], errors="coerce").dropna().astype(float)
    q1, q3 = np.quantile(revenue.to_numpy(), [0.25, 0.75])
    iqr = float(q3 - q1)
    upper = float(q3 + 5.0 * iqr)
    lower = float(q1 - 5.0 * iqr)
    outlier_mask = revenue.index[(revenue > upper) | (revenue < lower)]
    outlier_rows = [int(value) for value in sales.loc[outlier_mask, "source_row"].tolist()]

    daily["month"] = daily["period"].astype(str).str.slice(0, 7)
    daily_by_month = daily.groupby("month", sort=True)["reported_revenue"].sum()
    monthly_by_month = monthly.set_index("period")["reported_revenue"].astype(float)
    breaks = []
    for period in sorted(set(daily_by_month.index) | set(monthly_by_month.index)):
        daily_value = float(daily_by_month.get(period, 0.0))
        monthly_value = float(monthly_by_month.get(period, 0.0))
        difference = round(monthly_value - daily_value, 2)
        if abs(difference) >= 0.01:
            breaks.append(
                {
                    "period": str(period),
                    "daily_total": round(daily_value, 2),
                    "monthly_total": round(monthly_value, 2),
                    "difference": difference,
                }
            )

    return {
        "data_origin": "Synthetic data",
        "input_directory": str(raw_dir.name),
        "sales_rows": int(len(sales)),
        "checks": {
            "missing_values": {
                "count": int(sum(missing_fields.values())),
                "by_field": missing_fields,
                "source_rows_by_field": missing_rows_by_field,
            },
            "duplicate_rows": {"count": len(duplicate_sources), "source_rows": duplicate_sources},
            "label_variants": {"count": len(label_variants), "entities": label_variants},
            "outliers": {
                "count": len(outlier_rows),
                "source_rows": outlier_rows,
                "method": "Revenue outside 5 times the interquartile range",
                "lower_bound": round(lower, 2),
                "upper_bound": round(upper, 2),
            },
            "reconciliation_breaks": {"count": len(breaks), "periods": breaks},
        },
    }


def write_qa_outputs(report: dict[str, Any], out_dir: Path) -> tuple[Path, Path]:
    qa_dir = out_dir / "qa"
    json_path = qa_dir / "qa_report.json"
    text_path = qa_dir / "qa_summary.txt"
    write_json(json_path, report)
    checks = report["checks"]
    lines = [
        "AnalystOS synthetic data quality summary",
        f"Data origin: {report['data_origin']}",
        f"Sales rows inspected: {report['sales_rows']}",
        f"Missing values: {checks['missing_values']['count']}",
        f"Duplicate rows: {checks['duplicate_rows']['count']}",
        f"Customer label groups with variants: {checks['label_variants']['count']}",
        f"Revenue outliers: {checks['outliers']['count']}",
        f"Monthly reconciliation breaks: {checks['reconciliation_breaks']['count']}",
        "Ground-truth issue manifest was not read by analysis.",
    ]
    text_path.parent.mkdir(parents=True, exist_ok=True)
    text_path.write_text("\n".join(lines) + "\n", encoding="utf-8", newline="\n")
    return json_path, text_path
