from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[1]
MARTS_PATH = ROOT / "semantic" / "marts.yml"
MART_ERD_PATH = ROOT / "semantic" / "marts_erd.md"

EXPECTED_COLUMNS = {
    "df_user_spine": 17,
    "df_exp_eval": 22,
    "df_weekly_panel": 14,
}


def test_marts_documentation_is_complete():
    document = yaml.safe_load(MARTS_PATH.read_text(encoding="utf-8"))
    assert document["version"] == 1
    assert set(document["marts"]) == set(EXPECTED_COLUMNS)

    for name, expected_columns in EXPECTED_COLUMNS.items():
        mart = document["marts"][name]
        assert mart["description"].strip()
        assert mart["grain"]
        assert mart["source_tables"]
        assert len(mart["columns"]) == expected_columns

        columns = set(mart["columns"])
        assert set(mart["grain"]).issubset(columns)
        keys = (
            mart["primary_key"]
            if isinstance(mart["primary_key"], list)
            else [mart["primary_key"]]
        )
        assert set(keys).issubset(columns)

        for column, metadata in mart["columns"].items():
            assert metadata["type"]
            assert metadata["semantics"].strip(), f"{name}.{column} lacks semantics"


def test_mart_relationship_diagram_exists():
    text = MART_ERD_PATH.read_text(encoding="utf-8")
    assert "```mermaid" in text
    assert "DF_USER_SPINE" in text
    assert "DF_EXP_EVAL" in text
    assert "DF_WEEKLY_PANEL" in text
