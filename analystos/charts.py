"""Headless, deterministic chart creation for synthetic analysis outputs."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import matplotlib

matplotlib.use("Agg")

import matplotlib.pyplot as plt
import numpy as np


def create_charts(results: dict[str, Any], qa: dict[str, Any], out_dir: Path) -> list[Path]:
    chart_dir = out_dir / "charts"
    chart_dir.mkdir(parents=True, exist_ok=True)
    output_paths: list[Path] = []
    metadata = {"Software": "AnalystOS"}

    months = results["monthly_revenue"]
    labels = [item["month"] for item in months]
    values = [float(item["revenue"]) for item in months]
    x = np.arange(len(labels))
    fig, ax = plt.subplots(figsize=(11, 5.5), constrained_layout=True)
    ax.plot(x, values, color="#176B87", linewidth=2.2, marker="o", markersize=3.5, label="Cleaned monthly revenue")
    event_counts = results["cleaning_event_counts_by_month"]
    event_month_index = {label: index for index, label in enumerate(labels)}
    low = min(values) if values else 0.0
    high = max(values) if values else 1.0
    marker_y = low - (high - low) * 0.10 if high > low else low * 0.85
    for month, count in event_counts.items():
        if month not in event_month_index:
            continue
        event_x = event_month_index[month]
        ax.scatter([event_x], [marker_y], color="#D97706", s=32, zorder=3)
        ax.annotate(
            f"{count} audit events",
            (event_x, marker_y),
            xytext=(0, -16 if event_x % 2 else -30),
            textcoords="offset points",
            ha="center",
            fontsize=7,
            color="#8A4B08",
        )
    ax.set_title("Synthetic data | Monthly revenue and cleaning events", loc="left", fontweight="bold")
    ax.set_xlabel("Transaction month")
    ax.set_ylabel("Revenue, synthetic USD units")
    ax.set_xticks(x[::2] if len(x) > 1 else x)
    ax.set_xticklabels(labels[::2] if len(labels) > 1 else labels, rotation=45, ha="right")
    ax.grid(axis="y", alpha=0.25)
    ax.legend(frameon=False, loc="upper left")
    path = chart_dir / "revenue_trend.png"
    fig.savefig(path, dpi=150, metadata=metadata)
    plt.close(fig)
    output_paths.append(path)

    checks = qa["checks"]
    qa_names = ["Missing cells", "Duplicate rows", "Label variant groups", "Revenue outliers", "Rollup breaks"]
    qa_keys = ["missing_values", "duplicate_rows", "label_variants", "outliers", "reconciliation_breaks"]
    qa_values = [int(checks[key]["count"]) for key in qa_keys]
    palette = ["#4C78A8", "#72B7B2", "#F2CF5B", "#E45756", "#B279A2"]
    fig, ax = plt.subplots(figsize=(9, 5), constrained_layout=True)
    bars = ax.barh(qa_names, qa_values, color=palette)
    ax.invert_yaxis()
    ax.set_title("Synthetic data | Quality checks", loc="left", fontweight="bold")
    ax.set_xlabel("Flagged records or groups")
    ax.grid(axis="x", alpha=0.25)
    for bar, count in zip(bars, qa_values):
        ax.text(max(float(bar.get_width()), 0.02) + 0.08, bar.get_y() + bar.get_height() / 2, str(count), va="center", fontsize=9)
    path = chart_dir / "qa_dashboard.png"
    fig.savefig(path, dpi=150, metadata=metadata)
    plt.close(fig)
    output_paths.append(path)

    cohorts = results["customer_cohorts"]
    matrix = np.array(cohorts["retention_pct"], dtype=float)
    masked = np.ma.masked_invalid(matrix)
    fig, ax = plt.subplots(figsize=(11, 7), constrained_layout=True)
    if matrix.size:
        image = ax.imshow(masked, aspect="auto", interpolation="nearest", cmap="Blues", vmin=0, vmax=100)
        fig.colorbar(image, ax=ax, label="Active customers as percent of cohort")
        ax.set_yticks(np.arange(len(cohorts["cohorts"])))
        ax.set_yticklabels(cohorts["cohorts"])
        ax.set_xticks(np.arange(len(cohorts["periods"])))
        ax.set_xticklabels([str(value) for value in cohorts["periods"]])
    ax.set_title("Synthetic data | Customer cohort retention", loc="left", fontweight="bold")
    ax.set_xlabel("Months since first purchase")
    ax.set_ylabel("First purchase month")
    path = chart_dir / "customer_cohorts.png"
    fig.savefig(path, dpi=150, metadata=metadata)
    plt.close(fig)
    output_paths.append(path)
    return output_paths
