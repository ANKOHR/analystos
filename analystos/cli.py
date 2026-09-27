"""Command-line entry point for AnalystOS."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

from analystos.generator import generate_data
from analystos.io_utils import read_json
from analystos.pipeline import run_pipeline
from analystos.qa import assess_data, write_qa_outputs
from analystos.report import generate_reports


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="analystos",
        description="Deterministic, traceable analysis of deliberately messy synthetic company data.",
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    generate = subparsers.add_parser("generate-data", help="create seeded synthetic CSV and SQLite inputs")
    generate.add_argument("--seed", type=int, default=42)
    generate.add_argument("--out", type=Path, default=Path("data"))

    qa = subparsers.add_parser("qa", help="inspect raw inputs and write a quality report")
    qa.add_argument("--data", type=Path, default=Path("data"))
    qa.add_argument("--out", type=Path, default=Path("build"))

    run = subparsers.add_parser("run", help="run QA, cleaning, analysis, charts, and reports")
    run.add_argument("--data", type=Path, default=Path("data"))
    run.add_argument("--out", type=Path, default=Path("build"))

    trace = subparsers.add_parser("trace", help="resolve a report claim to its evidence")
    trace.add_argument("claim_id")
    trace.add_argument("--out", type=Path, default=Path("build"))

    report = subparsers.add_parser("report", help="render Markdown and HTML from existing results")
    report.add_argument("--out", type=Path, default=Path("build"))
    report.add_argument("--format", choices=("both", "markdown", "html"), default="both")
    return parser


def _trace(claim_id: str, out_dir: Path) -> dict[str, Any]:
    claims_path = out_dir / "claims.json"
    results_path = out_dir / "results.json"
    if not claims_path.is_file() or not results_path.is_file():
        raise FileNotFoundError("claims.json and results.json are required; run the pipeline first")
    payload = read_json(claims_path)
    results = read_json(results_path)
    all_records = payload["claims"] + payload["assumptions"] + payload["hypotheses"]
    records = {item["id"]: item for item in all_records}
    if claim_id not in records:
        raise KeyError(f"Unknown claim or assumption ID: {claim_id}")
    record = records[claim_id]
    evidence_pointer = record.get("evidence_pointer")
    calculations = {item["id"]: item for item in results["calculations"]}
    evidence: Any = calculations.get(evidence_pointer)
    if evidence is None:
        evidence = records.get(evidence_pointer)
    resolved = {"record": record, "evidence": evidence}
    if evidence is None:
        raise KeyError(f"Evidence pointer {evidence_pointer} for {claim_id} does not resolve")
    if evidence_pointer in records:
        nested_pointer = evidence.get("evidence_pointer")
        resolved["nested_evidence"] = calculations.get(nested_pointer, records.get(nested_pointer))
    return resolved


def main(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    try:
        if args.command == "generate-data":
            outputs = generate_data(args.seed, args.out)
            print(
                json.dumps(
                    {
                        "data_origin": "Synthetic data",
                        "seed": args.seed,
                        "raw_directory": str(outputs["raw_dir"]),
                        "database": str(outputs["database"]),
                        "ground_truth_manifest": str(outputs["manifest"]),
                    },
                    sort_keys=True,
                )
            )
        elif args.command == "qa":
            report = assess_data(args.data)
            json_path, summary_path = write_qa_outputs(report, args.out)
            print(json.dumps({"data_origin": report["data_origin"], "qa_json": str(json_path), "summary": str(summary_path)}, sort_keys=True))
        elif args.command == "run":
            result = run_pipeline(args.data, args.out)
            print(
                json.dumps(
                    {
                        "data_origin": "Synthetic data",
                        "report_markdown": str(args.out / "report.md"),
                        "report_html": str(args.out / "report.html"),
                        "charts": [str(path) for path in result["charts"]],
                        "claims": len(result["analysis"]["claims"]["claims"]),
                    },
                    sort_keys=True,
                )
            )
        elif args.command == "trace":
            print(json.dumps(_trace(args.claim_id, args.out), ensure_ascii=False, indent=2, sort_keys=True))
        elif args.command == "report":
            outputs = generate_reports(args.out, args.format)
            print(json.dumps({"reports": [str(path) for path in outputs]}, sort_keys=True))
        return 0
    except (FileNotFoundError, KeyError, ValueError) as exc:
        print(f"analystos: {exc}")
        return 2


def cli_entry() -> None:
    raise SystemExit(main())
