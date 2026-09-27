# AnalystOS

AnalystOS is a deterministic, traceable analysis pipeline for deliberately messy synthetic company data. It generates roughly two years of synthetic sales, customer, product, and rollup records, audits data quality, applies logged cleaning rules, computes management metrics, and produces a report with charts and evidence references.

All generated records and all reports are labelled synthetic. No generated company or transaction represents a real business.

## Quickstart

From this directory in PowerShell:

~~~powershell
py -3.12 -m venv .venv
.\.venv\Scripts\python.exe -m pip install --disable-pip-version-check -r requirements.txt
.\.venv\Scripts\python.exe -m pip install --no-deps --no-build-isolation -e .
.\.venv\Scripts\analystos.exe generate-data --seed 42 --out data
.\.venv\Scripts\analystos.exe run --data data --out build
~~~

The full report is written to **build/report.md** and **build/report.html**. The three charts are in **build/charts/**. Inspect the quality summary at **build/qa/qa_summary.txt** and the field-level cleaning history at **build/cleaned/cleaning_audit.csv**.

Resolve a report reference to its calculation or assumption:

~~~powershell
.\.venv\Scripts\analystos.exe trace C-001 --out build
~~~

## Architecture

~~~text
                  generate-data --seed
                           |
                           v
       raw synthetic CSV files + company.sqlite
                           |
                           v
         deterministic QA and reconciliation
                           |
                           v
        rule-based cleaning + field audit log
                 |                     |
                 v                     v
          cleaned sales           review queue
                 |
                 v
     pandas and numpy calculations
       |             |             |
       v             v             v
   trends         cohorts       product mix
       \             |             /
        \            v            /
         traceable claims and hypotheses
                           |
                           v
       matplotlib charts + Markdown and HTML

 ground_truth/planted_issues.json -> tests only
~~~

The ground-truth manifest is separate from the raw analysis inputs. QA and the report do not read or display it. Tests use it to check that planted defects were detected.

## Example output

With seed 42, an example executive summary includes:

~~~text
Cleaned transaction revenue totals $1,865,569.30 in synthetic USD units. [C-001]
Revenue changed 12.12% between the opening and closing three-month windows. [C-002]
The cleaned sales data contains 20 purchasing customers. [C-003]
~~~

Each claim reference resolves to an exact formula, source, and result in **build/results.json** and **build/claims.json**. For example, the trace command for C-001 returns the cleaned revenue sum and its source file. Values can change if the seed or implementation changes.

## Commands

| Command | Purpose |
| --- | --- |
| analystos generate-data --seed 42 --out data | Create seeded CSV and SQLite inputs plus the separate test manifest. |
| analystos qa --data data --out build | Write the QA JSON and human-readable summary. |
| analystos run --data data --out build | Run QA, cleaning, modelling, charts, and reports. |
| analystos trace C-001 --out build | Resolve a claim, hypothesis, or assumption identifier. |
| analystos report --out build --format both | Render Markdown and HTML from existing calculations. |

The run command preserves each source transaction in either the cleaned dataset or the review queue. Repairs and quarantines are recorded in **cleaned/cleaning_audit.csv**. Missing unit prices use a labelled product-list-price assumption. Revenue outliers and duplicate transactions remain reviewable.

All random generation uses a local seeded NumPy generator. Analysis and charts run on CPU using pinned Python dependencies.

## Tests

Run the test suite with:

~~~powershell
.\.venv\Scripts\python.exe -m pytest
~~~
