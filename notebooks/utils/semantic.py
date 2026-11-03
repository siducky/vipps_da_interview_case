from __future__ import annotations

import argparse
import csv
from pathlib import Path
from typing import Any

import yaml

ROOT = Path(__file__).resolve().parents[2]
DEFAULT_MODEL_PATH = ROOT / "semantic" / "model.yml"
DEFAULT_EXAMPLES_PATH = ROOT / "semantic" / "examples.yml"
DEFAULT_DATA_DIR = ROOT / "data" / "raw"


class SemanticModelError(ValueError):
    """Raised when the semantic model is missing required information."""


def load_model(path: str | Path | None = None) -> dict[str, Any]:
    """Load the YAML semantic model."""
    model_path = Path(path) if path is not None else DEFAULT_MODEL_PATH
    with model_path.open(encoding="utf-8") as handle:
        model = yaml.safe_load(handle)
    if not isinstance(model, dict):
        raise SemanticModelError(f"{model_path} must contain a YAML mapping")
    return model


def load_examples(path: str | Path | None = None) -> list[dict[str, Any]]:
    """Load the natural-language to SQL examples."""
    examples_path = Path(path) if path is not None else DEFAULT_EXAMPLES_PATH
    with examples_path.open(encoding="utf-8") as handle:
        payload = yaml.safe_load(handle) or {}
    examples = payload.get("examples", [])
    if not isinstance(examples, list):
        raise SemanticModelError(f"{examples_path} must contain an 'examples' list")
    return examples


def _table_path(table: dict[str, Any], data_dir: Path) -> Path:
    raw_path = Path(table["file"])
    if raw_path.is_absolute():
        return raw_path
    return data_dir / raw_path.name


def _read_header(path: Path) -> list[str]:
    with path.open(newline="", encoding="utf-8") as handle:
        reader = csv.reader(handle)
        try:
            return next(reader)
        except StopIteration as exc:
            raise SemanticModelError(f"{path} is empty") from exc


def validate_model(
    model: dict[str, Any],
    data_dir: str | Path | None = None,
) -> None:
    """Validate the model against the raw CSV headers and relationships."""
    data_dir_path = Path(data_dir) if data_dir is not None else DEFAULT_DATA_DIR
    errors: list[str] = []

    for key in ("version", "tables", "metrics"):
        if key not in model:
            errors.append(f"Missing required top-level key: {key}")
    if errors:
        raise SemanticModelError(
            "Semantic model validation failed:\n"
            + "\n".join(f"- {error}" for error in errors)
        )

    tables = model["tables"]
    if not isinstance(tables, dict) or not tables:
        raise SemanticModelError("'tables' must be a non-empty mapping")

    for name, table in tables.items():
        if not isinstance(table, dict):
            errors.append(f"{name}: table definition must be a mapping")
            continue

        missing_keys = [
            key
            for key in ("file", "description", "grain", "primary_key", "columns")
            if key not in table
        ]
        for key in missing_keys:
            errors.append(f"{name}: missing required key '{key}'")
        if missing_keys:
            continue

        path = _table_path(table, data_dir_path)
        if not path.exists():
            errors.append(f"{name}: CSV not found at {path}")
            continue

        try:
            header = _read_header(path)
        except SemanticModelError as exc:
            errors.append(str(exc))
            continue

        columns = table["columns"]
        if not isinstance(columns, dict):
            errors.append(f"{name}: 'columns' must be a mapping")
            continue

        expected = list(columns)
        missing = sorted(set(header) - set(expected))
        extra = sorted(set(expected) - set(header))
        if missing:
            errors.append(
                f"{name}: CSV columns missing from model: {', '.join(missing)}"
            )
        if extra:
            errors.append(f"{name}: model columns missing from CSV: {', '.join(extra)}")

        primary_key = table["primary_key"]
        if primary_key not in columns:
            errors.append(
                f"{name}: primary key '{primary_key}' is not a documented column"
            )

        grain = table["grain"]
        if not isinstance(grain, list) or not grain:
            errors.append(f"{name}: 'grain' must be a non-empty list")
        else:
            for column in grain:
                if column not in columns:
                    errors.append(f"{name}: grain column '{column}' is not documented")
            if primary_key not in grain:
                errors.append(
                    f"{name}: primary key '{primary_key}' is not part of the grain"
                )

    for name, table in tables.items():
        if not isinstance(table, dict):
            continue
        columns = table.get("columns", {})
        if isinstance(columns, dict):
            for column_name, column in columns.items():
                if not isinstance(column, dict):
                    continue
                reference = column.get("references")
                if not reference:
                    continue
                if "." not in reference:
                    errors.append(
                        f"{name}.{column_name}: reference '{reference}' must be table.column"
                    )
                    continue
                reference_table, reference_column = reference.split(".", 1)
                if reference_table not in tables:
                    errors.append(
                        f"{name}.{column_name}: referenced table '{reference_table}' does not exist"
                    )
                    continue
                reference_columns = tables[reference_table].get("columns", {})
                if reference_column not in reference_columns:
                    errors.append(
                        f"{name}.{column_name}: referenced column '{reference}' does not exist"
                    )

        for join in table.get("joins", []):
            if not isinstance(join, dict):
                errors.append(f"{name}: join entry must be a mapping")
                continue
            target = join.get("to")
            local_key = join.get("local_key")
            remote_key = join.get("remote_key")
            relationship = join.get("relationship")
            if target not in tables:
                errors.append(f"{name}: join target '{target}' does not exist")
                continue
            if local_key not in columns:
                errors.append(
                    f"{name}: local join column '{local_key}' is not documented"
                )
            target_columns = tables[target].get("columns", {})
            if remote_key not in target_columns:
                errors.append(
                    f"{name}: remote join column '{remote_key}' is not documented in {target}"
                )
            if relationship not in {
                "one_to_one",
                "one_to_many",
                "many_to_one",
                "many_to_many",
            }:
                errors.append(f"{name}: invalid relationship '{relationship}'")

    metrics = model["metrics"]
    if not isinstance(metrics, dict) or not metrics:
        errors.append("'metrics' must be a non-empty mapping")
    else:
        for name, metric in metrics.items():
            if not isinstance(metric, dict):
                errors.append(f"metric {name}: definition must be a mapping")
                continue
            for key in ("description", "table", "expression"):
                if key not in metric:
                    errors.append(f"metric {name}: missing '{key}'")
            if metric.get("table") not in tables:
                errors.append(
                    f"metric {name}: table '{metric.get('table')}' does not exist"
                )

    if errors:
        raise SemanticModelError(
            "Semantic model validation failed:\n"
            + "\n".join(f"- {error}" for error in errors)
        )


def connect(
    db_path: str | Path = ":memory:",
    data_dir: str | Path | None = None,
    model: dict[str, Any] | None = None,
):
    """Create DuckDB views over the raw CSVs and return a connection."""
    try:
        import duckdb
    except ImportError as exc:
        raise RuntimeError(
            "duckdb is required to build the semantic layer. Install it with 'uv sync'."
        ) from exc

    semantic_model = model if model is not None else load_model()
    data_dir_path = Path(data_dir) if data_dir is not None else DEFAULT_DATA_DIR
    path_str = str(db_path)

    if path_str != ":memory:":
        Path(path_str).parent.mkdir(parents=True, exist_ok=True)

    connection = duckdb.connect(path_str)
    try:
        for name, table in semantic_model["tables"].items():
            csv_path = _table_path(table, data_dir_path)
            if not csv_path.exists():
                raise FileNotFoundError(f"CSV not found for {name}: {csv_path}")
            escaped_path = str(csv_path).replace("'", "''")
            quoted_name = name.replace('"', '""')
            connection.execute(
                f'CREATE OR REPLACE VIEW "{quoted_name}" AS '
                f"SELECT * FROM read_csv_auto('{escaped_path}', header = true)"
            )
    except Exception:
        connection.close()
        raise

    return connection


def build_db(
    db_path: str | Path,
    data_dir: str | Path | None = None,
    model: dict[str, Any] | None = None,
) -> Path:
    """Build a local DuckDB database with one view per semantic table."""
    connection = connect(db_path, data_dir=data_dir, model=model)
    connection.close()
    return Path(db_path)


def model_summary(model: dict[str, Any] | None = None) -> str:
    """Return a compact, human-readable summary of the semantic model."""
    semantic_model = model if model is not None else load_model()
    lines = [f"# {semantic_model.get('name', 'Semantic model')}"]
    description = semantic_model.get("description")
    if description:
        lines.append(str(description).strip())

    for name, table in semantic_model["tables"].items():
        grain = ", ".join(table["grain"])
        lines.append(f"\n## {name}")
        lines.append(table["description"])
        lines.append(f"Grain: {grain}")
        lines.append(f"Columns: {', '.join(table['columns'])}")
        for join in table.get("joins", []):
            optional = " (optional)" if join.get("optional") else ""
            lines.append(
                f"Join: {join['local_key']} -> {join['to']}.{join['remote_key']} "
                f"[{join['relationship']}]{optional}"
            )
        for caveat in table.get("caveats", []):
            lines.append(f"- {caveat}")

    lines.append("\n## Metrics")
    for name, metric in semantic_model["metrics"].items():
        lines.append(f"- {name}: {metric['expression']}")

    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Validate the Vipps semantic model and build DuckDB views."
    )
    parser.add_argument(
        "--model", type=Path, default=None, help="Path to semantic/model.yml"
    )
    parser.add_argument(
        "--data-dir",
        type=Path,
        default=None,
        help="Directory containing the raw CSV files",
    )
    parser.add_argument(
        "--validate",
        action="store_true",
        help="Validate the model against the CSV files",
    )
    parser.add_argument(
        "--build-db",
        type=Path,
        default=None,
        help="Build a DuckDB database at this path",
    )
    parser.add_argument(
        "--summary", action="store_true", help="Print a summary of the semantic model"
    )
    args = parser.parse_args(argv)

    model = load_model(args.model)

    if args.validate or args.build_db:
        validate_model(model, data_dir=args.data_dir)
        print("Semantic model is valid.")

    if args.build_db:
        build_db(args.build_db, data_dir=args.data_dir, model=model)
        print(f"Built DuckDB database at {args.build_db}")

    if args.summary:
        print(model_summary(model))

    if not (args.validate or args.build_db or args.summary):
        parser.print_help()

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
