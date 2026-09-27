from __future__ import annotations

import csv
import json
import re
from pathlib import Path

from analystos.cli import main
from analystos.cleaning import clean_sales
from analystos.generator import generate_data
from analystos.pipeline import run_pipeline
from analystos.qa import assess_data, write_qa_outputs


def _read_csv(path: Path) -> list[dict[str, str]]:
    with path.open("r", encoding="utf-8", newline="") as handle:
        return list(csv.DictReader(handle))


def test_generator_reproducibility_including_sqlite(project_temp_dir: Path):
    first = project_temp_dir / "first"
    second = project_temp_dir / "second"
    generate_data(42, first)
    generate_data(42, second)
    first_files = {path.relative_to(first).as_posix(): path.read_bytes() for path in first.rglob("*") if path.is_file()}
    second_files = {path.relative_to(second).as_posix(): path.read_bytes() for path in second.rglob("*") if path.is_file()}
    assert first_files == second_files
    assert "raw/company.sqlite" in first_files


def test_qa_catches_each_manifest_issue(project_temp_dir: Path):
    data_dir = project_temp_dir / "data"
    outputs = generate_data(42, data_dir)
    manifest = json.loads(outputs["manifest"].read_text(encoding="utf-8"))
    qa = assess_data(data_dir)
    checks = qa["checks"]
    by_type = {issue["type"]: issue for issue in manifest["planted_issues"]}

    missing = by_type["missing_values"]
    assert checks["missing_values"]["count"] >= len(missing["fields"])
    for field in missing["fields"]:
        assert missing["source_rows"][0] in checks["missing_values"]["source_rows_by_field"][field]

    duplicate = by_type["duplicate_rows"]
    assert duplicate["source_rows"][1] in checks["duplicate_rows"]["source_rows"]

    variants = by_type["label_variants"]
    assert any(
        entity["customer_id"] == variants["entity_id"]
        and set(variants["labels"]).issubset(set(entity["labels"]))
        for entity in checks["label_variants"]["entities"]
    )

    outlier = by_type["outliers"]
    assert set(outlier["source_rows"]).issubset(set(checks["outliers"]["source_rows"]))

    conflict = by_type["conflicting_totals"]
    assert any(item["period"] == conflict["period"] for item in checks["reconciliation_breaks"]["periods"])
    assert checks["reconciliation_breaks"]["count"] >= 1
    assert "ground_truth" not in qa


def test_cleaning_audit_is_complete_and_rows_are_accounted_for(project_temp_dir: Path):
    data_dir = project_temp_dir / "data"
    outputs = generate_data(42, data_dir)
    qa = assess_data(data_dir)
    cleaned = clean_sales(data_dir, project_temp_dir / "run", qa)
    raw_rows = _read_csv(outputs["raw_dir"] / "sales.csv")
    clean_rows = _read_csv(cleaned["cleaned_path"])
    review_rows = _read_csv(cleaned["review_path"])
    audit_rows = _read_csv(cleaned["audit_path"])
    raw_by_row = {row["source_row"]: row for row in raw_rows}
    output_by_row = {row["source_row"]: row for row in clean_rows + review_rows}
    audit_by_row: dict[str, list[dict[str, str]]] = {}
    for event in audit_rows:
        audit_by_row.setdefault(event["row_id"], []).append(event)

    assert len(raw_rows) == len(clean_rows) + len(review_rows)
    assert set(raw_by_row) == set(output_by_row)
    assert cleaned["audit_events"] == len(audit_rows)
    for row_id, row_events in audit_by_row.items():
        for event in row_events:
            if event["field"] == "__row__":
                assert row_id in {row["source_row"] for row in review_rows}
                assert event["new_value"] == "retained_in_review_queue"
            else:
                assert event["old_value"] != event["new_value"]
                assert row_id in output_by_row
                assert output_by_row[row_id][event["field"]] == event["new_value"]

    for row in review_rows:
        assert any(event["field"] == "__row__" for event in audit_by_row[row["source_row"]])
        assert row["reason"]

    missing_source = next(
        row_id
        for field, row_ids in qa["checks"]["missing_values"]["source_rows_by_field"].items()
        for row_id in row_ids
        if field == "unit_price"
    )
    assert any(event["field"] == "unit_price" for event in audit_by_row[str(missing_source)])
    assert any(event["field"] == "revenue" for event in audit_by_row[str(missing_source)])


def test_pipeline_is_deterministic_and_produces_full_reports(project_temp_dir: Path):
    data_dir = project_temp_dir / "data"
    generate_data(42, data_dir)
    first = run_pipeline(data_dir, project_temp_dir / "first_run")
    second = run_pipeline(data_dir, project_temp_dir / "second_run")

    for relative in ["report.md", "report.html", "results.json", "claims.json"]:
        assert (project_temp_dir / "first_run" / relative).read_bytes() == (
            project_temp_dir / "second_run" / relative
        ).read_bytes()
    assert [path.name for path in first["charts"]] == [
        "revenue_trend.png",
        "qa_dashboard.png",
        "customer_cohorts.png",
    ]
    assert all(path.is_file() and path.stat().st_size > 1000 for path in first["charts"])
    report = (project_temp_dir / "first_run" / "report.md").read_text(encoding="utf-8")
    assert "Synthetic data only" in report
    assert "Executive summary" in report
    assert "Methods appendix" in report
    assert first["cleaning"]["quarantined_rows"] >= 2
    assert chr(0x2013) not in report
    assert chr(0x2014) not in report


def test_every_sample_report_claim_resolves_with_trace(project_temp_dir: Path, capsys):
    data_dir = project_temp_dir / "data"
    out_dir = project_temp_dir / "run"
    generate_data(42, data_dir)
    run_pipeline(data_dir, out_dir)
    report = (out_dir / "report.md").read_text(encoding="utf-8")
    identifiers = sorted(set(re.findall(r"\[\^(C-\d{3}|A-\d{3}|HYP-\d{3})\]", report)))
    assert identifiers
    for identifier in identifiers:
        assert main(["trace", identifier, "--out", str(out_dir)]) == 0
        traced = json.loads(capsys.readouterr().out)
        assert traced["record"]["id"] == identifier
        assert traced["evidence"] is not None


def test_cli_smoke_for_every_subcommand(project_temp_dir: Path, capsys):
    data_dir = project_temp_dir / "cli_data"
    qa_dir = project_temp_dir / "cli_qa"
    out_dir = project_temp_dir / "cli_run"
    assert main(["generate-data", "--seed", "42", "--out", str(data_dir)]) == 0
    assert "Synthetic data" in capsys.readouterr().out
    assert main(["qa", "--data", str(data_dir), "--out", str(qa_dir)]) == 0
    assert (qa_dir / "qa" / "qa_report.json").is_file()
    capsys.readouterr()
    assert main(["run", "--data", str(data_dir), "--out", str(out_dir)]) == 0
    assert (out_dir / "report.md").is_file()
    capsys.readouterr()
    assert main(["report", "--out", str(out_dir), "--format", "both"]) == 0
    assert (out_dir / "report.html").is_file()
    capsys.readouterr()
    assert main(["trace", "C-001", "--out", str(out_dir)]) == 0
    assert json.loads(capsys.readouterr().out)["record"]["id"] == "C-001"


def test_project_sources_have_no_forbidden_dashes_or_gpu_imports():
    root = Path(__file__).resolve().parents[1]
    source_paths = list((root / "analystos").rglob("*.py")) + list((root / "tests").rglob("*.py"))
    docs_and_config = [root / "README.md", root / "requirements.txt", root / "pyproject.toml"]
    for path in source_paths + docs_and_config:
        text = path.read_text(encoding="utf-8")
        assert chr(0x2013) not in text
        assert chr(0x2014) not in text
    for path in source_paths:
        text = path.read_text(encoding="utf-8")
        assert not re.search(r"(?im)^\s*(?:import|from)\s+(?:torch|cuda)\b", text)
