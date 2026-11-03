# Vipps Data Analyst Interview Case

Siddhant's solution to the Vipps VIP loyalty case: does VIP membership create
lasting loyalty?


The repository contains the full analysis notebook, an 11-slide interactive
deck, three analytical marts, a documented semantic model, a PNG plot archive,
and the tests and checks that keep all of it honest. Everything is generated
from the immutable CSVs in `data/raw/`; no analysis step is manual.

**Status:** complete. Analysis, deck, marts, plots, semantic model and tests are
in place, and `make check` and `make test` pass.

## Contents

| Deliverable | Path | What it is |
|---|---|---|
| Analysis workbook | [`notebooks/case_analysis.py`](notebooks/case_analysis.py) | EDA, data-quality checks, event study, experiment evaluation, sizing, mart appendix |
| Interactive deck | [`notebooks/vip_presentation.py`](notebooks/vip_presentation.py) | 11 slides, live widgets, Vipps visual identity |
| Static deck layout | [`notebooks/layouts/vip_presentation.slides.json`](notebooks/layouts/vip_presentation.slides.json) | Slide ordering and per-cell settings |
| Analytical marts | `data/processed/*.csv` | Generated on every analysis run (git-ignored) |
| Semantic model | [`semantic/model.yml`](semantic/model.yml) | Tables, joins, metrics, dimensions |
| Mart dictionary | [`semantic/marts.yml`](semantic/marts.yml) | Grain, keys, types, semantics for each mart column |
| ER diagrams | [`semantic/erd.md`](semantic/erd.md), [`semantic/marts_erd.md`](semantic/marts_erd.md) | Mermaid diagrams for raw tables and marts |
| Model viewer | [`notebooks/data_model.py`](notebooks/data_model.py) | Renders the ERD and dictionary |
| Plot archive | [`plots/`](plots/README.md) | 12 PNGs grouped by question |
| Plot exporter | [`scripts/export_plots.py`](scripts/export_plots.py) | Rebuilds `plots/` from the deck's charts |
| Data notes | [`data/README.md`](data/README.md) | Provenance, file grain, row counts, column dictionary |

## The question

The case asks whether VIP is creating loyalty or selecting for it, and what the
team should do next. The work is split into three questions:

1. **Q1 — Selection.** Do future VIP members already behave differently before
   they enrol?
2. **Q2 — Causal effect.** Among invited users, does invitation change sign-up,
   retention and spend?
3. **Q3 — Next steps.** Where is the commercial headroom, and what should be
   tested next?

## Quickstart

Requires [uv](https://docs.astral.sh/uv/) and Python 3.14 (pinned in
`.python-version`; `uv` installs it for you).

```bash
make setup       # create .venv and sync dependencies from pyproject.toml
make notebook    # open the analysis workbook
```

Other entry points:

```bash
make app         # read-only app mode for the analysis workbook
make model       # open the data model viewer
make check       # semantic tests + marimo checks + ruff lint/format
make test        # pytest (20 tests)
make db          # build data/processed/vipps.duckdb views from the semantic model
make export      # check, then build reports/case_analysis.html and site/ (WASM)
make clean       # remove site/ and caches
```

Targets are lowercase and case-sensitive; `make` alone prints the menu. The deck
has no dedicated target, so open it directly:

```bash
uv run marimo edit notebooks/vip_presentation.py
```

For a read-only presentation, use `uv run marimo run notebooks/vip_presentation.py`.

## Regenerate everything

The pipeline is a straight line. Each step reads what the previous one wrote:

```text
data/raw/*.csv
      │  DuckDB (in memory, SQL only)
      ▼
data/processed/df_user_spine.csv       419 users × 17 cols
data/processed/df_exp_eval.csv         269 experiment users × 22 cols
data/processed/df_weekly_panel.csv     20,725 user-weeks × 14 cols
      │
      ├──▶ notebooks/case_analysis.py   (EDA → Q1 → Q2 → Q3 → mart appendix)
      ├──▶ notebooks/vip_presentation.py (11 slides, reads the marts)
      └──▶ plots/*.png                   (scripts/export_plots.py)
```

To rebuild from scratch:

```bash
rm -rf data/processed                    # start clean, optional
make setup
uv run marimo export html notebooks/case_analysis.py -o reports/case_analysis.html
uv run --with vl-convert-python python scripts/export_plots.py
make check && make test
```

The `marimo export` command executes the whole analysis headlessly, which is
what writes the three marts. Running `make notebook` and using marimo's
**Run all** does the same thing interactively.

The deck does not require `data/processed/` to exist: if the CSVs are missing it
rebuilds the identical marts in memory from `data/raw/` in its own setup cell, so
it can be opened and presented on a fresh clone.

## Repository map

```text
vipps_da_interview_case/
├── Case_Brief.pdf                  # original case prompt
├── Makefile                        # every routine command
├── pyproject.toml                  # dependencies, ruff and pytest config
├── data/
│   ├── raw/                        # immutable case CSVs + data dictionary PDF
│   ├── processed/                  # generated marts (git-ignored)
│   └── README.md                   # provenance, grain, row counts, columns
├── notebooks/
│   ├── case_analysis.py            # main analysis workbook
│   ├── vip_presentation.py         # 11-slide deck
│   ├── data_model.py               # ERD / dictionary viewer
│   ├── layouts/                    # slides layout for the deck
│   └── utils/semantic.py           # semantic-model loader and DuckDB builder
├── semantic/
│   ├── model.yml                   # raw-data model and metric definitions
│   ├── examples.yml                # verified natural-language → SQL examples
│   ├── erd.md                      # raw-data ER diagram
│   ├── marts.yml                   # mart grain, keys, columns, semantics
│   └── marts_erd.md                # mart ER diagram
├── plots/                          # exported PNGs, grouped by question
├── scripts/export_plots.py         # PNG exporter (vl-convert)
├── tests/                          # semantic-model and mart-doc tests
├── reports/                        # static HTML backup (make export-html)
└── agent_prompts/                  # working notes from the case, not analysis code
```

## Notebooks

### `case_analysis.py`

Ten sections plus an appendix, in the order a reviewer would want them:

| Section | Content |
|---|---|
| 1. Data quality and grain | Row counts, nulls, duplicates, referential integrity, cutoff handling |
| 2. Transactions overview | Volume, ticket size, monthly trend |
| 3. Purchase values and channel mix | Distributions, online vs in person, take rates |
| 4. Users | Age, country, VIP cohorts, observation coverage |
| 5. Merchants | Concentration, category mix |
| 6. MCC popularity by age bucket | Category preference heat map |
| 7. Selection bias and pre/post VIP event study | 7A future VIPs vs never-VIPs, 7B within-user change around enrolment |
| 8. Invitation experiment: waves and take-up | 8A right-censoring, 8B sign-up by wave and arm, 8C cumulative sign-up |
| 9. Experiment: retention and spend | 9A forest plot of % lift with 95% confidence intervals |
| 10. Channel economics and next steps | 10A take rate by category, 10B cross-sell sizing, 10C structured summary |
| Appendix | Analytical mart dictionary rendered from `semantic/marts.yml` |

The notebook writes the three marts to `data/processed/` as a side effect of
running, which is why it must run before the deck if you want the CSVs on disk.

### `vip_presentation.py`

Eleven slides, 16:9, no vertical scrolling at the deck's width (`medium`,
≈1345 × 756 CSS px):

1. Title: *Does VIP create lasting customer loyalty?*
2. Executive summary: four findings, one recommendation.
3. Context: channel mix and where the money is.
4. Retention framework: what "coming back" means, silence days and survival.
5. Q1: future VIPs were already heavier shoppers (pre-launch comparison).
6. Q1: within-user event study around enrolment.
7. Q2: invitation experiment design and take-up.
8. Q2: 16-week ITT outcomes (purchases, GMV, retention) with confidence intervals.
9. Q3: channel economics and an illustrative online cross-sell scenario.
10. Q3: deferred analyses and why they were deferred.
11. Appendix: sources, lineage and the AI-assisted workflow.

Every slide except 1, 2 and 11 owns its widgets: sliders and toggles named
`ui_sN_*` are read only by `slide_N`, so moving a control reruns one slide, not
the deck. The slide counter badge in each header is a static `NN / 11`.

The deck uses the Vipps palette throughout: `#FFFAF7` canvas, `#0B1F3A` navy,
`#FF5B24` orange, `#2F6DB3` blue, `#526176` body text, `#8C8C8C` muted.

## Data

### Raw files

Immutable inputs in `data/raw/` (see [`data/README.md`](data/README.md) for the
full dictionary):

| File | Rows | Grain |
|---|---:|---|
| `transactions.csv` | 350,567 | One completed purchase |
| `users.csv` | 419 | One user |
| `merchants.csv` | 30 | One merchant |
| `mcc.csv` | 6 | One merchant category code |
| `experiment_exposure.csv` | 269 | One VIP invitation assignment |
| `cards.csv` | 1,203 | One payment card (deferred, see slide 10) |

Data period: purchases during 2025, cutoff `2026-01-01 00:00:00` exclusive. The
dataset is synthetic; fee percentages and NOK values are fictional and do not
represent Vipps economics.

### Analytical marts

Built with DuckDB SQL inside the notebook and written to `data/processed/`.

| Mart | Grain | Rows | Columns |
|---|---|---:|---:|
| `df_user_spine` | One row per user | 419 | 17 |
| `df_exp_eval` | One row per experiment user | 269 | 22 |
| `df_weekly_panel` | One row per user-week (balanced) | 20,725 | 14 |

Each column's type and meaning is in [`semantic/marts.yml`](semantic/marts.yml).
The marts are git-ignored: they are derived, cheap to rebuild, and must never be
edited by hand.

## Methods and definitions

**Cohorts.** A user is a VIP member if `vip_enrolled` is true (195 of 419). An
experiment user is anyone in `experiment_exposure` (269: 226 in the July/August
wave, 43 in December). Coverage matters: 385 users have purchases observable
from 2025-01-01 (`is_full_year_obs`), and 34 start later, so they are excluded
from full-year comparisons.

**Event study (Q1).** Weekly purchases and GMV are aligned to each VIP member's
enrolment week (week 0) and averaged across users with a complete ±8-week window.
No synthetic control group is drawn; the point is the within-user shape.

**Experiment (Q2).** Intent-to-treat comparison of invited vs control users over
16 weeks from exposure, on weekly purchases, weekly GMV, active-week share and
28-day retention. Take-up is reported separately because roughly 8% of control
users enrol without an invitation.

**Statistical tools.** Only transparent, textbook tests are used:

- Two-sample Welch t-test (`scipy.stats.ttest_ind`, `equal_var=False`) for
  between-group comparisons of means.
- Paired t-test (`scipy.stats.ttest_rel`) for within-user pre/post comparisons.
- Pooled two-proportion z-test for sign-up rates.
- Normal-approximation 95% confidence intervals: `diff ± 1.96 × se`.
- Complier-scaled ITT: divide the ITT effect by the net sign-up lift (0.602) to
  approximate the effect on actual joiners.

**Deliberately not used.** No regression adjustment, no propensity matching, no
Wilson intervals, no round-robin or synthetic-control matching. With 269
experiment users each of those would add machinery and opacity without adding
identifying power. Where a point estimate is not significant, the deck says so
rather than dressing it up.

## Headline findings

- **Selection dominates the raw gap.** Before VIP launched, future VIP members
  already spent 1.09× more per week and bought 1.10× more often than never-VIPs
  (Jan–Apr, full-year users). The full-year gap is not evidence of a VIP effect.
- **Invitation works as a nudge.** In the summer wave, sign-up rose from 8.0%
  (control) to 68.1% (invited), +60.2 pp, p < 0.001.
- **The loyalty effect is not yet visible.** Over 16 weeks the invitation changed
  purchases by +4.7% (p = 0.50), GMV by −0.5% (p = 0.96) and 28-day retention by
  +10.7% (p = 0.25). All intervals cross zero: the direction is plausible, the
  evidence is thin.
- **Online is the thinner but scalable margin.** Take rate is 1.95% online versus
  1.29% in person; online is 30.7% of GMV. Cross-selling online is the lever worth
  testing, and only at a point cost well under the take rate (50 bps of GMV is
  ~26% of the online fee).

## Deferred analyses

Each was considered and parked, with the reason on slide 10:

- **`cards.csv` (1,203 rows).** Card status exists only at the 2026-01-01 cutoff,
  so using it would leak future information into 2025 behaviour; it is also
  card-level, not user-level. Revisit when card history exists.
- **16 age buckets.** 419 users across 16 four-year bands is ~26 per band and ~7
  per experiment arm, too few to compare reliably. Revisit with wider bands or
  pooled years.
- **December retention.** 43 users exposed in December have too little
  post-exposure observation before the cutoff. Revisit in Q1 2026.

## Plot archive

`plots/` holds 12 PNGs generated from the deck's Altair charts, grouped by
question, with an index in [`plots/README.md`](plots/README.md):

```bash
uv run --with vl-convert-python python scripts/export_plots.py
```

The exporter executes the deck headlessly, reads each Vega-Lite spec from the
rendered HTML, and rasterises it. Charts are matched by **title**, so if you
rename a chart, update `MAPPING` in `scripts/export_plots.py` or it will be
skipped.

## Checks, tests and formatting

```bash
make check   # pytest tests/test_semantic.py, marimo check, ruff lint + format
make test    # full pytest suite (20 tests)
```

`make check` covers the semantic model, both notebooks in `notebooks/` that it
lists, and ruff across the repository. The deck is linted and format-checked by
the same ruff run; run marimo's own check on it with:

```bash
uv run marimo check notebooks/vip_presentation.py
```

The tests verify that `semantic/marts.yml` documents every mart and column, that
grain and primary keys are declared, and that the semantic model and its SQL
examples stay valid.

Two configuration details are intentional:

- `notebooks/*.py` ignore ruff's `PLR1711`, because marimo writes a bare
  `return` at the end of display cells to mark the output.
- `.opencode` is excluded from ruff: it holds agent tooling and vendored skill
  docs, not project code.

Notebook cells are kept as fixed points. marimo's serializer adds one blank line
before the generated `return`, so stored cell code carries no trailing newline.
After editing a notebook, confirm it round-trips:

```bash
uv run python -c "
from marimo._convert.converters import MarimoConvert
src = open('notebooks/vip_presentation.py').read()
print('roundtrip:', MarimoConvert.from_py(src).to_py() == src)"
```

## Reproducibility notes

- Raw files are never modified; every transformation is in notebook or script
  code, under version control.
- SQL is used for joins and aggregations; Python only for tests and chart data.
  No step depends on crosstab defaults, locale or file ordering: anything
  ordered has an explicit `ORDER BY` or `sort`.
- Money stays in NOK as `Decimal`-preserving floats read from CSV; percentages
  and bps conversions are explicit (`bps / 10 000`).
- Dates are parsed as datetimes; the analysis is cutoff-based, not
  timezone-based, so no timezone conversion is applied (documented in
  `data/README.md`).
- The marts are deterministic given the raw CSVs, so re-running the notebook
  regenerates byte-identical columns and row counts.
- Exports (`reports/`, `site/`, `plots/`) are build artefacts, not sources.

## AI-assisted workflow

AI models accelerated the SQL scaffolding, the marimo UI and the Altair/CSS
layout (Gemini 4 Argon for framing and methodology critique, DeepSeek V4.1 for
implementation). Every number in the deck was then re-derived and checked by
hand against the raw data: row and null counts against `data/README.md`,
degenerate metrics rejected, late-coverage and right-censored cohorts isolated,
and black-box estimators replaced with the transparent t-tests listed above.
The analysis is only as good as those checks, not the tool that typed it.

## Limitations

- The data is synthetic and spans one year, so seasonality and long-run loyalty
  cannot be separated.
- The experiment covers two waves with different follow-up lengths; the December
  wave informs take-up, not retention.
- Take-up among invited users is high, but complier scaling is an approximation,
  not an instrumental-variables estimate.
- 195 VIP members (189 with full-year coverage) is a small group; subgroup
  findings are directional at best.
- Channel mix and take rates are descriptive; they size an opportunity, they do
  not forecast it.

## Data and confidentiality

The case data is synthetic and uses fictional merchants. Confirm permission
before publishing raw files. Do not commit real customer data, PII, credentials
or confidential fields. This repository is not affiliated with Vipps.
>>>>>>> 16f345c (first iteration case study)
