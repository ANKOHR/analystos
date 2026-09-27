"""Create deterministic, intentionally messy synthetic company data."""

from __future__ import annotations

import sqlite3
from datetime import date
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

from analystos.io_utils import write_csv, write_json

DATA_LABEL = "SYNTHETIC DATA"
SALES_FIELDS = [
    "source_row",
    "sale_id",
    "sale_date",
    "customer_id",
    "customer_label",
    "product_id",
    "quantity",
    "unit_price",
    "revenue",
    "data_label",
]


def _money(value: float) -> float:
    return round(float(value) + 1e-10, 2)


def _write_database(path: Path, tables: dict[str, tuple[list[str], list[dict[str, Any]]]], seed: int) -> None:
    if path.exists():
        path.unlink()
    connection = sqlite3.connect(path)
    try:
        connection.execute("PRAGMA journal_mode=DELETE")
        connection.execute("PRAGMA synchronous=FULL")
        connection.execute("CREATE TABLE metadata (key TEXT PRIMARY KEY, value TEXT NOT NULL)")
        connection.executemany(
            "INSERT INTO metadata(key, value) VALUES (?, ?)",
            [("data_label", DATA_LABEL), ("seed", str(seed))],
        )
        for table, (columns, rows) in tables.items():
            quoted = ", ".join('"' + column.replace('"', '""') + '"' for column in columns)
            definitions = ", ".join(f'"{column}" TEXT' for column in columns)
            connection.execute(f'CREATE TABLE "{table}" ({definitions})')
            placeholders = ", ".join("?" for _ in columns)
            values = [tuple(None if row[column] is None else str(row[column]) for column in columns) for row in rows]
            connection.executemany(f'INSERT INTO "{table}" ({quoted}) VALUES ({placeholders})', values)
        connection.commit()
        connection.execute("VACUUM")
    finally:
        connection.close()


def generate_data(seed: int, out_dir: Path) -> dict[str, Path]:
    """Generate CSV and SQLite analysis inputs plus a separate issue manifest."""
    rng = np.random.default_rng(seed)
    raw_dir = out_dir / "raw"
    truth_dir = out_dir / "ground_truth"
    raw_dir.mkdir(parents=True, exist_ok=True)
    truth_dir.mkdir(parents=True, exist_ok=True)

    customer_names = [
        "Acme Ltd",
        "Northstar Group",
        "Bluebird Foods",
        "Cedar Works",
        "Harbor and Hill",
        "Mosaic Supply",
        "Juniper House",
        "Redwood Retail",
        "Silverline Labs",
        "Fieldstone Co",
        "Brightpath Studio",
        "Westlake Services",
        "Pinecone Partners",
        "Orchard Systems",
        "Summit Goods",
        "Openwater Trading",
        "Lighthouse Media",
        "Granite Peak Ltd",
        "Meadowcraft",
        "Evergreen Office",
    ]
    customers = [
        {
            "customer_id": f"C{index:03d}",
            "customer_name": name,
            "segment": ["SMB", "Mid-market", "Enterprise"][index % 3],
            "data_label": DATA_LABEL,
        }
        for index, name in enumerate(customer_names)
    ]
    product_specs = [
        ("P001", "Analytics Suite", "Software", 79.00),
        ("P002", "Team Workspace", "Software", 42.50),
        ("P003", "Support Plan", "Services", 125.00),
        ("P004", "Onboarding", "Services", 210.00),
        ("P005", "Data Connector", "Software", 34.00),
        ("P006", "Training Session", "Services", 165.00),
        ("P007", "Secure Storage", "Software", 24.00),
        ("P008", "Advisory Hours", "Services", 185.00),
    ]
    products = [
        {
            "product_id": product_id,
            "product_name": product_name,
            "category": category,
            "list_price": price,
            "data_label": DATA_LABEL,
        }
        for product_id, product_name, category, price in product_specs
    ]
    name_by_id = {row["customer_id"]: row["customer_name"] for row in customers}
    price_by_id = {row["product_id"]: row["list_price"] for row in products}

    sales: list[dict[str, Any]] = []
    dates = pd.date_range("2024-01-01", "2025-12-31", freq="D")
    for current_day in dates:
        transaction_count = int(rng.integers(4, 9))
        for _ in range(transaction_count):
            customer_index = int(rng.integers(0, len(customers)))
            product_index = int(rng.integers(0, len(products)))
            customer_id = customers[customer_index]["customer_id"]
            product_id = products[product_index]["product_id"]
            quantity = int(rng.integers(1, 8))
            unit_price = _money(price_by_id[product_id] * float(rng.uniform(0.88, 1.12)))
            label = name_by_id[customer_id]
            if customer_id == "C000" and int(rng.integers(0, 4)) == 0:
                label = "ACME LTD"
            source_row = len(sales)
            sales.append(
                {
                    "source_row": source_row,
                    "sale_id": f"S{source_row:06d}",
                    "sale_date": current_day.date().isoformat(),
                    "customer_id": customer_id,
                    "customer_label": label,
                    "product_id": product_id,
                    "quantity": quantity,
                    "unit_price": unit_price,
                    "revenue": _money(quantity * unit_price),
                    "data_label": DATA_LABEL,
                }
            )

    missing_row = 17
    outlier_row = 31
    sales[missing_row]["unit_price"] = None
    sales[missing_row]["revenue"] = None
    sales[outlier_row]["quantity"] = 999
    sales[outlier_row]["revenue"] = _money(999 * sales[outlier_row]["unit_price"])

    duplicate_original = 25
    duplicate = dict(sales[duplicate_original])
    duplicate_row = len(sales)
    duplicate["source_row"] = duplicate_row
    sales.append(duplicate)

    daily_totals: dict[str, float] = {}
    for row in sales:
        daily_totals[row["sale_date"]] = daily_totals.get(row["sale_date"], 0.0) + (row["revenue"] or 0.0)
    daily_rollups = [
        {"period": period, "reported_revenue": _money(total), "data_label": DATA_LABEL}
        for period, total in sorted(daily_totals.items())
    ]
    monthly_totals: dict[str, float] = {}
    for row in daily_rollups:
        month = row["period"][:7]
        monthly_totals[month] = monthly_totals.get(month, 0.0) + row["reported_revenue"]
    conflict_month = "2025-07"
    monthly_totals[conflict_month] += 8750.00
    monthly_rollups = [
        {"period": period, "reported_revenue": _money(total), "data_label": DATA_LABEL}
        for period, total in sorted(monthly_totals.items())
    ]

    csv_tables = {
        "customers": (["customer_id", "customer_name", "segment", "data_label"], customers),
        "products": (["product_id", "product_name", "category", "list_price", "data_label"], products),
        "sales": (SALES_FIELDS, sales),
        "daily_rollups": (["period", "reported_revenue", "data_label"], daily_rollups),
        "monthly_rollups": (["period", "reported_revenue", "data_label"], monthly_rollups),
    }
    for table, (fields, rows) in csv_tables.items():
        write_csv(raw_dir / f"{table}.csv", rows, fields)
    database_path = raw_dir / "company.sqlite"
    _write_database(database_path, csv_tables, seed)

    manifest = {
        "data_origin": DATA_LABEL,
        "seed": seed,
        "manifest_purpose": "Test scoring only. This file is not an analysis input.",
        "planted_issues": [
            {"type": "missing_values", "table": "sales", "source_rows": [missing_row], "fields": ["unit_price", "revenue"]},
            {"type": "duplicate_rows", "table": "sales", "source_rows": [duplicate_original, duplicate_row]},
            {"type": "label_variants", "table": "sales", "entity_id": "C000", "labels": ["Acme Ltd", "ACME LTD"]},
            {"type": "outliers", "table": "sales", "source_rows": [outlier_row], "field": "revenue"},
            {"type": "conflicting_totals", "table": "monthly_rollups", "period": conflict_month, "offset": 8750.00},
        ],
    }
    manifest_path = truth_dir / "planted_issues.json"
    write_json(manifest_path, manifest)
    return {"raw_dir": raw_dir, "database": database_path, "manifest": manifest_path}

