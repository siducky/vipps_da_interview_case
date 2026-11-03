from __future__ import annotations

import copy
import re
from pathlib import Path

import duckdb
import pytest

from notebooks.utils.semantic import (
    DEFAULT_DATA_DIR,
    SemanticModelError,
    build_db,
    connect,
    load_examples,
    load_model,
    model_summary,
    validate_model,
)

ERD_PATH = Path(__file__).resolve().parents[1] / "semantic" / "erd.md"


def _parse_erd_columns(path: Path) -> dict[str, set[str]]:
    """Return the columns documented for each entity in the Mermaid ERD."""
    text = path.read_text(encoding="utf-8")
    mermaid = text.split("```mermaid", 1)[1].split("```", 1)[0]
    entities: dict[str, set[str]] = {}
    for match in re.finditer(
        r"^\s{4}([A-Z_]+)\s*\{\n(.*?)^\s{4}\}", mermaid, re.MULTILINE | re.DOTALL
    ):
        entities[match.group(1).lower()] = set(
            re.findall(r"^\s+\S+\s+(\w+)", match.group(2), re.MULTILINE)
        )
    return entities


@pytest.fixture(scope="session")
def model():
    return load_model()


@pytest.fixture(scope="session")
def con(model):
    connection = connect(":memory:", data_dir=DEFAULT_DATA_DIR, model=model)
    yield connection
    connection.close()


def test_model_structure(model):
    assert model["version"] == 1
    assert set(model["tables"]) == {
        "transactions",
        "users",
        "merchants",
        "mcc",
        "cards",
        "experiment_exposure",
    }
    assert model["metrics"]


def test_model_matches_csv_headers(model):
    validate_model(model, data_dir=DEFAULT_DATA_DIR)


def test_erd_documents_all_model_columns(model):
    erd_columns = _parse_erd_columns(ERD_PATH)
    assert set(erd_columns) == set(model["tables"])
    for table_name, table in model["tables"].items():
        assert erd_columns[table_name] == set(table["columns"]), (
            f"{table_name}: ERD columns differ from model.yml"
        )


def test_primary_keys_are_unique(model, con):
    for name, table in model["tables"].items():
        primary_key = table["primary_key"]
        duplicates = con.execute(
            f'SELECT count(*) - count(DISTINCT "{primary_key}") FROM "{name}"'
        ).fetchone()[0]
        assert duplicates == 0, f"{name}.{primary_key} has duplicate values"


def test_foreign_keys_resolve(model, con):
    for name, table in model["tables"].items():
        for column_name, column in table["columns"].items():
            reference = column.get("references")
            if not reference:
                continue
            reference_table, reference_column = reference.split(".", 1)
            orphan_count = con.execute(
                f"""
                SELECT count(*)
                FROM "{name}" AS source
                LEFT JOIN "{reference_table}" AS target
                  ON source."{column_name}" = target."{reference_column}"
                WHERE source."{column_name}" IS NOT NULL
                  AND target."{reference_column}" IS NULL
                """
            ).fetchone()[0]
            assert orphan_count == 0, f"{name}.{column_name} has orphan values"


def test_correct_card_join_preserves_transaction_grain(con):
    transactions = con.execute("SELECT count(*) FROM transactions").fetchone()[0]
    joined = con.execute(
        """
        SELECT count(*)
        FROM transactions AS t
        JOIN cards AS c ON t.payment_source_id = c.payment_source_id
        """
    ).fetchone()[0]
    assert joined == transactions


def test_incorrect_card_join_would_fan_out(con):
    transactions = con.execute("SELECT count(*) FROM transactions").fetchone()[0]
    multi_card_users = con.execute(
        """
        SELECT count(*)
        FROM (
            SELECT user_id
            FROM cards
            GROUP BY user_id
            HAVING count(*) > 1
        )
        """
    ).fetchone()[0]
    assert multi_card_users > 0

    joined = con.execute(
        """
        SELECT count(*)
        FROM transactions AS t
        JOIN cards AS c ON t.user_id = c.user_id
        """
    ).fetchone()[0]
    assert joined > transactions


EXAMPLES = load_examples()


@pytest.mark.parametrize(
    "example",
    EXAMPLES,
    ids=[example["question"] for example in EXAMPLES],
)
def test_examples_execute(example, con):
    rows = con.execute(example["sql"]).fetchall()
    assert rows


def test_summary_mentions_all_tables(model):
    summary = model_summary(model)
    for name in model["tables"]:
        assert name in summary


def test_validation_rejects_undocumented_column(model):
    bad_model = copy.deepcopy(model)
    bad_model["tables"]["transactions"]["columns"]["not_a_real_column"] = {
        "type": "string",
        "description": "Intentional test column.",
    }
    with pytest.raises(SemanticModelError):
        validate_model(bad_model, data_dir=DEFAULT_DATA_DIR)


def test_build_db(model, tmp_path):
    db_path = tmp_path / "vipps.duckdb"
    build_db(db_path, data_dir=DEFAULT_DATA_DIR, model=model)
    assert db_path.exists()

    connection = duckdb.connect(str(db_path), read_only=True)
    try:
        count = connection.execute("SELECT count(*) FROM transactions").fetchone()[0]
    finally:
        connection.close()
    assert count == 350567
