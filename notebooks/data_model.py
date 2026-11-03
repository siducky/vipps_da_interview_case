import marimo

__generated_with = "0.25.2"
app = marimo.App(width="medium")


@app.cell
def _():
    from pathlib import Path

    import marimo as mo

    return Path, mo


@app.cell
def _(Path, mo):
    notebook_dir = mo.notebook_dir()
    if notebook_dir is None:
        raise RuntimeError("Cannot locate the notebook directory")

    erd_path = Path(notebook_dir).parent / "semantic" / "erd.md"
    text = erd_path.read_text(encoding="utf-8")

    start = text.index("```mermaid") + len("```mermaid")
    end = text.index("```", start)
    diagram = text[start:end].strip()
    return diagram, erd_path


@app.cell
def _(erd_path, mo):
    source = erd_path.relative_to(erd_path.parents[1])
    mo.md(
        f"""
        # Data Model for Fictional Payment Company

        Entity-relationship diagram sourced from `{source}`.
        """
    )
    return


@app.cell
def _(diagram, mo):
    mo.mermaid(diagram)
    return


if __name__ == "__main__":
    app.run()
