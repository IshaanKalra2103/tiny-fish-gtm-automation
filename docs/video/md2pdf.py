# /// script
# requires-python = ">=3.11"
# dependencies = ["markdown"]
# ///
"""Render the recording sheets (Markdown) to plain A4/Letter PDFs with headless Chromium.

usage (repo root): uv run docs/video/md2pdf.py docs/video/recording-brief.md docs/video/dylan-lines.md ...
Writes <name>.pdf next to each .md. Uses the Playwright that web/ already installs.
"""
import subprocess
import sys
import tempfile
from pathlib import Path

import markdown

CSS = """
@page { size: Letter; margin: 18mm 18mm 20mm 18mm; }
body { font: 11.5pt/1.5 -apple-system, "Helvetica Neue", Arial, sans-serif; color: #111; }
h1 { font-size: 20pt; margin: 0 0 6pt; }
h2 { font-size: 13.5pt; margin: 18pt 0 6pt; padding-top: 6pt; border-top: 1px solid #ddd; break-after: avoid; }
p, li { margin: 4pt 0; }
ul { padding-left: 16pt; }
blockquote { margin: 4pt 0 10pt; padding: 6pt 10pt; border-left: 3px solid #111; background: #f5f5f5;
  font-size: 12.5pt; line-height: 1.5; break-inside: avoid; }
blockquote p { margin: 3pt 0; }
p:has(+ blockquote) { break-after: avoid; margin-top: 10pt; }
table { border-collapse: collapse; width: 100%; font-size: 10pt; margin: 6pt 0; }
th, td { border: 1px solid #ccc; padding: 4pt 6pt; text-align: left; vertical-align: top; }
th { background: #f0f0f0; }
code { font: 10pt Menlo, monospace; }
"""

PRINT = """
import { createRequire } from 'node:module';
const { chromium } = createRequire(process.argv[2])('@playwright/test');
const [,, , html, pdf] = process.argv;
const b = await chromium.launch({ headless: true });
const p = await b.newPage();
await p.goto('file://' + html, { waitUntil: 'load' });
await p.pdf({ path: pdf, format: 'Letter', printBackground: true, displayHeaderFooter: true,
  headerTemplate: '<span></span>',
  footerTemplate: '<div style="font-size:8pt;color:#888;width:100%;text-align:center"><span class="pageNumber"></span> / <span class="totalPages"></span></div>',
  margin: { top: '18mm', bottom: '20mm', left: '18mm', right: '18mm' } });
await b.close();
"""


def main() -> None:
    root = Path(__file__).resolve().parents[2]
    pkg = root / "web" / "package.json"
    with tempfile.TemporaryDirectory() as td:
        js = Path(td) / "print.mjs"
        js.write_text(PRINT)
        for a in sys.argv[1:]:
            md = Path(a).resolve()
            body = markdown.markdown(md.read_text(), extensions=["tables", "sane_lists"])
            html = Path(td) / (md.stem + ".html")
            html.write_text(f"<!doctype html><meta charset=utf-8><title>{md.stem}</title><style>{CSS}</style>{body}")
            pdf = md.with_suffix(".pdf")
            subprocess.run(["node", str(js), str(pkg), str(html), str(pdf)], check=True)
            print("wrote", pdf.relative_to(root))


if __name__ == "__main__":
    main()
