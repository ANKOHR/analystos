"""Human-readable Markdown and HTML reports with traceable claim footnotes."""

from __future__ import annotations

import html
import re
from pathlib import Path
from typing import Any

from analystos.io_utils import read_json


def _inline_html(value: str) -> str:
    escaped = html.escape(value, quote=True)
    return re.sub(r"\*\*(.+?)\*\*", r"<strong>\1</strong>", escaped)


def markdown_to_html(markdown: str) -> str:
    lines = markdown.splitlines()
    body: list[str] = []
    in_list = False
    for line in lines:
        image_match = re.fullmatch(r"!\[([^\]]*)\]\(([^)]+)\)", line.strip())
        footnote_match = re.fullmatch(r"\[\^([^\]]+)\]:\s*(.*)", line.strip())
        if line.startswith("- "):
            if not in_list:
                body.append("<ul>")
                in_list = True
            body.append(f"<li>{_inline_html(line[2:])}</li>")
            continue
        if in_list:
            body.append("</ul>")
            in_list = False
        if not line.strip():
            continue
        if image_match:
            alt = html.escape(image_match.group(1), quote=True)
            src = html.escape(image_match.group(2), quote=True)
            body.append(f'<figure><img src="{src}" alt="{alt}"><figcaption>{alt}</figcaption></figure>')
        elif footnote_match:
            body.append(f'<p class="footnote" id="{html.escape(footnote_match.group(1))}">{_inline_html(footnote_match.group(2))}</p>')
        elif line.startswith("### "):
            body.append(f"<h3>{_inline_html(line[4:])}</h3>")
        elif line.startswith("## "):
            body.append(f"<h2>{_inline_html(line[3:])}</h2>")
        elif line.startswith("# "):
            body.append(f"<h1>{_inline_html(line[2:])}</h1>")
        elif line.startswith("> "):
            body.append(f'<p class="notice">{_inline_html(line[2:])}</p>')
        elif line.strip() == "---":
            body.append("<hr>")
        else:
            body.append(f"<p>{_inline_html(line)}</p>")
    if in_list:
        body.append("</ul>")
    return """<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>AnalystOS Management Report: Synthetic Data</title>
<style>
body{font:16px/1.6 system-ui,sans-serif;color:#1d2939;max-width:980px;margin:40px auto;padding:0 24px}
h1,h2,h3{color:#123b52;line-height:1.25}h1{border-bottom:3px solid #176b87;padding-bottom:12px}
.notice{background:#eef6f8;padding:14px 18px;border-left:4px solid #176b87}
li{margin:7px 0}.footnote{font-size:.92em;color:#475467;border-left:2px solid #d0d5dd;padding-left:12px}
figure{margin:28px 0}img{max-width:100%;height:auto;border:1px solid #eaecf0}figcaption{font-size:.9em;color:#475467}
hr{border:0;border-top:1px solid #d0d5dd;margin:28px 0}
</style>
</head>
<body>
""" + "\n".join(body) + "\n</body>\n</html>\n"


def build_markdown(results: dict[str, Any], claims_payload: dict[str, Any]) -> str:
    claims = {item["id"]: item for item in claims_payload["claims"]}
    hypotheses = claims_payload["hypotheses"]
    assumptions = claims_payload["assumptions"]
    c = {f"C-{index:03d}": claims[f"C-{index:03d}"] for index in range(1, 11)}
    trend = next(item for item in results["calculations"] if item["id"] == "CALC-002")["result"]
    reconciliation = next(item for item in results["calculations"] if item["id"] == "CALC-007")["result"]
    period_text = ", ".join(
        f"{item['period']} (difference {item['difference']:,.2f})" for item in reconciliation["periods"]
    ) or "no months"
    first_window = ", ".join(trend["first_months"])
    last_window = ", ".join(trend["last_months"])
    lines = [
        "# AnalystOS Management Report: Synthetic Data",
        "> Synthetic data only. The values and company records in this report are generated for demonstration and do not describe a real business.",
        "",
        "## Executive summary",
        f"- Cleaned transaction revenue totals **{c['C-001']['display_value']}** in synthetic USD units. [^C-001]",
        f"- Revenue changed **{c['C-002']['display_value']}** between the opening and closing three-month windows. [^C-002]",
        f"- The cleaned sales data contains **{c['C-003']['display_value']}** purchasing customers, with a repeat-customer share of **{c['C-004']['display_value']}**. [^C-003] [^C-004]",
        f"- **{c['C-006']['display_value']}** transaction rows are retained in a review queue with reasons. [^C-006]",
        "",
        "## Key findings",
        f"- The leading product category is **{c['C-005']['value']['category']}**, representing **{c['C-005']['value']['share_pct']:,.2f}%** of cleaned revenue. [^C-005]",
        f"- QA found **{c['C-007']['display_value']}** monthly rollup reconciliation breaks. The affected periods and differences are {period_text}. [^C-007]",
        f"- QA flagged **{c['C-008']['display_value']}** extreme revenue rows. These remain in the review queue and are excluded from cleaned transaction totals. [^C-008] [^C-006]",
        f"- The revenue chart annotates **{c['C-010']['display_value']}**, and cohort retention values are available by first purchase month. [^C-010] [^C-009]",
        "",
        "## Hypotheses",
    ]
    for hypothesis in hypotheses:
        lines.append(
            f"- **{hypothesis['classification']}**: {hypothesis['text']} [^{hypothesis['id']}] "
            f"Evidence: {hypothesis['evidence_pointer']}. {hypothesis['caveat']}"
        )
    lines.extend(
        [
            "",
            "## Risks and assumptions register",
            f"- **A-001**: {assumptions[0]['text']} It affects missing-price repair and should be reviewed against source billing records. [^A-001]",
            f"- **A-002**: {assumptions[1]['text']} Treat the trend as descriptive, not causal. [^A-002]",
            "- Duplicate transactions and flagged revenue outliers are visible in the review queue rather than silently removed. [^C-006] [^C-008]",
            "",
            "## Visual review",
            "The charts use the same cleaned calculations and quality checks referenced above.",
            "",
            "### Revenue trend and cleaning events",
            "![Synthetic monthly revenue and cleaning events](charts/revenue_trend.png)",
            "",
            "### Quality checks",
            "![Synthetic data quality checks](charts/qa_dashboard.png)",
            "",
            "### Customer cohorts",
            "![Synthetic customer cohort retention](charts/customer_cohorts.png)",
            "",
            "## Methods appendix",
            "- Revenue sums use repaired, cleaned transaction rows. Excluded rows remain in the review queue with a reason and an audit event. [^C-001] [^C-006]",
            f"- The trend calculation compares the first three and final three available monthly totals: {first_window}; then {last_window}. [^C-002]",
            "- Product mix is the cleaned revenue sum joined to the synthetic product category table. [^C-005]",
            "- Cohorts group customers by first purchase month and show each later month's active customers as a share of that cohort. [^C-009]",
            "- QA checks missing values, exact duplicate transactions, customer label variants, revenue outliers, and daily-to-monthly rollup differences. [^C-008] [^C-007]",
            "- Every changed field is recorded in the cleaning audit CSV. The full calculation and assumption records are in results JSON and claims JSON. [^C-010] [^A-001]",
            "",
            "## Traceability notes",
            "Each claim or assumption identifier resolves with analystos trace <claim-id> from this run's output directory.",
            "",
        ]
    )
    for claim in claims.values():
        lines.append(f"[^{claim['id']}]: {claim['text']}. Evidence pointer: {claim['evidence_pointer']}.")
    for item in hypotheses:
        lines.append(f"[^{item['id']}]: {item['classification']}. Evidence pointer: {item['evidence_pointer']}.")
    for item in assumptions:
        lines.append(f"[^{item['id']}]: Assumption. {item['basis']} Evidence pointer: {item['evidence_pointer']}.")
    return "\n".join(lines) + "\n"


def generate_reports(out_dir: Path, format_name: str = "both") -> list[Path]:
    results_path = out_dir / "results.json"
    claims_path = out_dir / "claims.json"
    if not results_path.is_file() or not claims_path.is_file():
        raise FileNotFoundError("results.json and claims.json are required; run the pipeline first")
    markdown = build_markdown(read_json(results_path), read_json(claims_path))
    outputs = []
    if format_name in {"both", "markdown"}:
        path = out_dir / "report.md"
        path.write_text(markdown, encoding="utf-8", newline="\n")
        outputs.append(path)
    if format_name in {"both", "html"}:
        path = out_dir / "report.html"
        path.write_text(markdown_to_html(markdown), encoding="utf-8", newline="\n")
        outputs.append(path)
    return outputs
