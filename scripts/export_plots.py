"""Export every chart in the VIP presentation deck to PNGs.

Charts are grouped into folders by the business question they support.
The notebooks are executed headlessly, the Vega-Lite specs are read from the
rendered HTML, and each spec is rasterised with vl-convert.

Usage:
    uv run --with vl-convert-python python scripts/export_plots.py
"""

from __future__ import annotations

import html
import json
import re
import subprocess
import sys
import tempfile
from pathlib import Path

import vl_convert as vlc

ROOT = Path(__file__).resolve().parents[1]
NOTEBOOK = ROOT / "notebooks" / "vip_presentation.py"
ANALYSIS_NOTEBOOK = ROOT / "notebooks" / "case_analysis.py"
PLOTS_DIR = ROOT / "plots"

# title in the Altair spec -> (folder, file stem)
MAPPING = {
    "Channel mix by selected population": (
        "01_context",
        "01_channel_mix_shares",
    ),
    "The churn cliff": (
        "01_context",
        "02_churn_cliff",
    ),
    "Weekly purchases around enrollment": (
        "02_q1_vip_selection",
        "01_event_study_weekly_purchases",
    ),
    "Weekly GMV around enrollment": (
        "02_q1_vip_selection",
        "02_event_study_weekly_gmv",
    ),
    "Enrollment rate by experiment arm": (
        "03_q2_invitation_experiment",
        "01_enrollment_rate_by_arm",
    ),
    "Cumulative enrollment over time": (
        "03_q2_invitation_experiment",
        "02_cumulative_enrollment",
    ),
    "Invitation vs. control · 16-week window": (
        "03_q2_invitation_experiment",
        "03_effect_forest_itt",
    ),
    "GMV share by sector": (
        "04_q3_next_steps",
        "01_gmv_share_by_sector",
    ),
    "Monthly GMV and average order value": (
        "05_summary_statistics",
        "01_monthly_gmv_and_aov",
    ),
    "Monthly active users (MAU)": (
        "05_summary_statistics",
        "02_monthly_active_users",
    ),
    "Purchase value distribution": (
        "05_summary_statistics",
        "03_purchase_value_distribution",
    ),
    "Users by age bucket": (
        "05_summary_statistics",
        "04_users_by_age_bucket",
    ),
}

FOLDER_NOTES = {
    "01_context": "Product and data context: channel mix and the churn cliff.",
    "02_q1_vip_selection": (
        "Question 1: do VIP joiners buy more? The within-user event study "
        "around VIP enrollment."
    ),
    "03_q2_invitation_experiment": (
        "Question 2: does inviting people help them keep using us? Take-up, "
        "cumulative enrollment and ITT effect estimates."
    ),
    "04_q3_next_steps": (
        "Question 3: what should the team do next? Channel economics and "
        "where the revenue opportunity sits."
    ),
    "05_summary_statistics": (
        "Descriptive summary statistics from the analysis notebook: "
        "transaction trend, active users, purchase values and age mix."
    ),
}

SPEC_PATTERN = r"data-mime='[^']*vegalite[^']*' data-data='([^']*)'"

FILE_NOTES = {
    "01_context/02_churn_cliff.png": (
        "Share of inter-purchase silences reaching a threshold that never "
        "return before the 2026-01-01 cutoff, as the threshold grows."
    ),
    "02_q1_vip_selection/01_event_study_weekly_purchases.png": (
        "Lines show only the VIP members with a complete +/-8 week window; no "
        "synthetic comparison group is plotted."
    ),
    "02_q1_vip_selection/02_event_study_weekly_gmv.png": (
        "Lines show only the VIP members with a complete +/-8 week window; no "
        "synthetic comparison group is plotted."
    ),
    "03_q2_invitation_experiment/03_effect_forest_itt.png": (
        "Points are % lift versus the control mean; horizontal bars are 95% "
        "confidence intervals; the dashed line is zero."
    ),
}


def _export_html(notebook: Path, destination: Path) -> None:
    subprocess.run(
        [
            sys.executable,
            "-m",
            "marimo",
            "export",
            "html",
            str(notebook),
            "-o",
            str(destination),
        ],
        check=True,
        cwd=ROOT,
    )


def _extract_specs(html_text: str):
    for raw in re.findall(SPEC_PATTERN, html_text):
        decoded = html.unescape(raw.encode().decode("unicode_escape"))
        try:
            spec = json.loads(json.loads(decoded))
        except json.JSONDecodeError:
            continue
        yield spec


def _title(spec: dict) -> str:
    title = spec.get("title")
    if isinstance(title, dict):
        return str(title.get("text", ""))
    if title:
        return str(title)
    for layer in spec.get("layer", []):
        layer_title = _title(layer)
        if layer_title:
            return layer_title
    return ""


def main() -> int:
    PLOTS_DIR.mkdir(exist_ok=True)
    specs = []
    with tempfile.TemporaryDirectory() as tmp:
        for _notebook in (NOTEBOOK, ANALYSIS_NOTEBOOK):
            html_path = Path(tmp) / f"{_notebook.stem}.html"
            _export_html(_notebook, html_path)
            specs.extend(_extract_specs(html_path.read_text(encoding="utf-8")))

    if not specs:
        print("No charts found in the rendered notebooks.", file=sys.stderr)
        return 1

    written = []
    seen = set()
    for spec in specs:
        title = _title(spec)
        if title not in MAPPING:
            continue
        folder, stem = MAPPING[title]
        key = f"{folder}/{stem}.png"
        if key in seen:
            continue
        seen.add(key)
        output = PLOTS_DIR / folder / f"{stem}.png"
        output.parent.mkdir(parents=True, exist_ok=True)
        if "width" not in spec:
            spec["width"] = 620
        output.write_bytes(vlc.vegalite_to_png(json.dumps(spec), scale=2))
        written.append((folder, output.name, title))

    readme_lines = [
        "# Plot exports",
        "",
        "Generated from `notebooks/vip_presentation.py` with",
        "`uv run --with vl-convert-python python scripts/export_plots.py`.",
        "",
        "Each folder groups the charts for one business question.",
        "",
    ]
    for folder in sorted({item[0] for item in written}):
        readme_lines.append(f"## `{folder}`")
        note = FOLDER_NOTES.get(folder)
        if note:
            readme_lines.append(note)
        readme_lines.append("")
        for _folder, filename, title in written:
            if _folder == folder:
                readme_lines.append(f"- `{filename}` - {title}")
                note = FILE_NOTES.get(f"{_folder}/{filename}")
                if note:
                    readme_lines.append(f"  {note}")
        readme_lines.append("")

    (PLOTS_DIR / "README.md").write_text("\n".join(readme_lines), encoding="utf-8")
    print(f"Exported {len(written)} charts into {PLOTS_DIR}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
