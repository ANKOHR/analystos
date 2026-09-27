"""Run the complete deterministic synthetic-data analysis pipeline."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from analystos.analytics import analyze
from analystos.charts import create_charts
from analystos.cleaning import clean_sales
from analystos.io_utils import write_json
from analystos.qa import assess_data, write_qa_outputs
from analystos.report import generate_reports


def run_pipeline(data_dir: Path, out_dir: Path) -> dict[str, Any]:
    raw_dir = data_dir / "raw" if (data_dir / "raw").is_dir() else data_dir
    required = ["sales.csv", "customers.csv", "products.csv", "daily_rollups.csv", "monthly_rollups.csv"]
    absent = [name for name in required if not (raw_dir / name).is_file()]
    if absent:
        raise FileNotFoundError(f"Missing synthetic data inputs in {raw_dir}: {', '.join(absent)}")

    qa = assess_data(data_dir)
    qa_json, qa_text = write_qa_outputs(qa, out_dir)
    cleaning = clean_sales(data_dir, out_dir, qa)
    analysis = analyze(cleaning["cleaned_path"], data_dir, cleaning, qa, out_dir)
    charts = create_charts(analysis["results"], qa, out_dir)
    reports = generate_reports(out_dir, "both")
    metadata_path = out_dir / "run_metadata.json"
    metadata = {
        "data_origin": "Synthetic data",
        "pipeline": ["raw", "qa", "cleaning", "modelling", "exploration", "hypotheses", "visualisation", "report"],
        "outputs": {
            "qa_json": "qa/qa_report.json",
            "qa_summary": "qa/qa_summary.txt",
            "cleaned_sales": "cleaned/sales_clean.csv",
            "review_queue": "cleaned/review_queue.csv",
            "cleaning_audit": "cleaned/cleaning_audit.csv",
            "results": "results.json",
            "claims": "claims.json",
            "charts": [str(path.relative_to(out_dir)).replace("\\", "/") for path in charts],
            "reports": [path.name for path in reports],
        },
        "row_counts": {
            "cleaned": cleaning["cleaned_rows"],
            "quarantined": cleaning["quarantined_rows"],
            "audit_events": cleaning["audit_events"],
        },
    }
    write_json(metadata_path, metadata)
    return {
        "qa": qa,
        "cleaning": cleaning,
        "analysis": analysis,
        "charts": charts,
        "reports": reports,
        "qa_json": qa_json,
        "qa_text": qa_text,
        "metadata": metadata_path,
    }

