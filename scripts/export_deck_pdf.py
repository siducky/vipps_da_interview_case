"""Export the VIP deck to a 16:9 PDF at the repository root.

marimo's own `marimo export pdf --as=slides` renders reveal at its default
960x700 stage, which letterboxes the deck into a 4:3 page. This script instead
prints the deck as a viewer sees it:

1. execute the notebook to a self-contained HTML file (outputs included);
2. open that file in headless Chromium and visit each slide;
3. screenshot the slide canvas (1345x756 CSS px, the deck's design size) at 2x;
4. stitch the pages into one PDF.

Usage:
    uv run --with playwright --with pillow python scripts/export_deck_pdf.py

Requires a Chromium build for Playwright (`uv run --with playwright playwright
install chromium`). Widget controls and reveal's navigation chrome are hidden so
the pages show the charts at their default settings.
"""

from __future__ import annotations

import argparse
import asyncio
import subprocess
import sys
import tempfile
from pathlib import Path

from PIL import Image
from playwright.async_api import async_playwright

ROOT = Path(__file__).resolve().parents[1]
NOTEBOOK = ROOT / "notebooks" / "vip_presentation.py"
DEFAULT_OUT = ROOT / "vip_presentation.pdf"

# reveal sizes its stage from the window width minus marimo's app gutter, so a
# 1433px window yields the deck's design canvas of 1345x756 CSS px.
VIEWPORT = {"width": 1433, "height": 1000}
DEVICE_SCALE = 2
SLIDES = 11
RESOLUTION = 200.0  # dpi used to size the PDF page from the pixels

HIDE_CHROME = """
.reveal .controls, .reveal .progress, .reveal .slide-number { display: none !important; }
marimo-ui-element { display: none !important; }
"""


def export_html(workdir: Path) -> Path:
    """Execute the notebook and write a self-contained HTML deck."""
    target = workdir / "deck.html"
    subprocess.run(
        [
            sys.executable,
            "-m",
            "marimo",
            "export",
            "html",
            str(NOTEBOOK),
            "-o",
            str(target),
        ],
        check=True,
        cwd=ROOT,
    )
    return target


async def capture(deck: Path, workdir: Path) -> list[Path]:
    """Screenshot every slide at the deck's design size."""
    shots: list[Path] = []
    async with async_playwright() as pw:
        browser = await pw.chromium.launch()
        page = await browser.new_page(
            viewport=VIEWPORT, device_scale_factor=DEVICE_SCALE
        )
        for index in range(SLIDES):
            await page.goto(f"file://{deck}#/{index}")
            await page.wait_for_timeout(2500)  # let Altair finish rendering
            await page.add_style_tag(content=HIDE_CHROME)
            await page.wait_for_timeout(300)
            box = await page.evaluate(
                """() => {
                    const rect = document
                        .querySelector('.reveal .slides section.present')
                        .getBoundingClientRect();
                    return {x: rect.x, y: rect.y, width: rect.width, height: rect.height};
                }"""
            )
            path = workdir / f"slide_{index + 1:02d}.png"
            await page.screenshot(path=path, clip={k: round(v) for k, v in box.items()})
            shots.append(path)
            print(
                f"slide {index + 1}/{SLIDES}: {box['width']:.0f}x{box['height']:.0f} CSS px"
            )
        await browser.close()
    return shots


def assemble(shots: list[Path], out: Path) -> None:
    """Stitch the slide images into a single PDF."""
    pages = [Image.open(path).convert("RGB") for path in shots]
    pages[0].save(out, save_all=True, append_images=pages[1:], resolution=RESOLUTION)
    print(f"wrote {out} ({out.stat().st_size / 1e6:.1f} MB, {len(pages)} pages)")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", type=Path, default=DEFAULT_OUT, help="output PDF path")
    args = parser.parse_args()

    with tempfile.TemporaryDirectory(prefix="vipps-deck-") as tmp:
        workdir = Path(tmp)
        deck = export_html(workdir)
        shots = asyncio.run(capture(deck, workdir))
        assemble(shots, args.out)


if __name__ == "__main__":
    main()
