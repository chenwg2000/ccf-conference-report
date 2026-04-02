#!/usr/bin/env python3
"""Convert report.md to a styled PDF using WeasyPrint."""

import markdown
from weasyprint import HTML, CSS
from pathlib import Path

BASE = Path(__file__).parent
MD_FILE = BASE / "report.md"
PDF_FILE = BASE / "CCF_A类会议调研报告.pdf"

md_text = MD_FILE.read_text(encoding="utf-8")

# Convert markdown to HTML
html_body = markdown.markdown(
    md_text,
    extensions=["tables", "fenced_code", "toc", "nl2br"],
)

CSS_STYLE = """
@import url('https://fonts.googleapis.com/css2?family=Noto+Sans+SC:wght@400;700&family=Source+Code+Pro&display=swap');

@page {
    size: A4;
    margin: 20mm 18mm 20mm 18mm;
    @bottom-center {
        content: counter(page) " / " counter(pages);
        font-size: 9pt;
        color: #888;
    }
}

* { box-sizing: border-box; }

body {
    font-family: "Noto Sans SC", "PingFang SC", "Microsoft YaHei", Arial, sans-serif;
    font-size: 10.5pt;
    line-height: 1.6;
    color: #222;
}

h1 {
    font-size: 18pt;
    font-weight: 700;
    color: #1a3a6b;
    border-bottom: 2px solid #1a3a6b;
    padding-bottom: 6px;
    margin-top: 0;
}

h2 {
    font-size: 13pt;
    font-weight: 700;
    color: #1a3a6b;
    border-left: 4px solid #1a3a6b;
    padding-left: 8px;
    margin-top: 24pt;
    page-break-after: avoid;
}

h3 {
    font-size: 11pt;
    font-weight: 700;
    color: #2c5f9e;
    margin-top: 14pt;
    page-break-after: avoid;
}

blockquote {
    background: #f0f4fb;
    border-left: 4px solid #2c5f9e;
    margin: 10pt 0;
    padding: 8pt 12pt;
    font-size: 9.5pt;
    color: #444;
}

table {
    width: 100%;
    border-collapse: collapse;
    font-size: 8.5pt;
    margin: 10pt 0;
    page-break-inside: auto;
}

thead tr {
    background-color: #1a3a6b;
    color: white;
}

thead th {
    padding: 5pt 6pt;
    text-align: center;
    font-weight: 600;
}

tbody tr:nth-child(even) {
    background-color: #f2f6fc;
}

tbody td {
    padding: 4pt 6pt;
    border-bottom: 1px solid #ddd;
    vertical-align: top;
}

tbody tr:hover {
    background-color: #e8eef8;
}

/* First column (number) */
tbody td:first-child {
    text-align: center;
    color: #666;
    width: 28pt;
}

/* Abbreviation column */
tbody td:nth-child(2) {
    font-weight: 600;
    color: #1a3a6b;
    white-space: nowrap;
}

/* Percentage column */
tbody td:last-child {
    text-align: center;
    font-weight: 600;
}

code {
    font-family: "Source Code Pro", "Courier New", monospace;
    background: #f5f5f5;
    padding: 1pt 3pt;
    border-radius: 2pt;
    font-size: 8.5pt;
}

hr {
    border: none;
    border-top: 1px solid #ccc;
    margin: 14pt 0;
}

p { margin: 6pt 0; }

ul, ol {
    margin: 6pt 0;
    padding-left: 20pt;
}

li { margin: 3pt 0; }

strong { color: #1a3a6b; }
"""

HTML_FULL = f"""<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="UTF-8">
<title>CCF A类会议调研报告</title>
</head>
<body>
{html_body}
</body>
</html>"""

print(f"Converting {MD_FILE.name} → {PDF_FILE.name} …")
HTML(string=HTML_FULL).write_pdf(
    str(PDF_FILE),
    stylesheets=[CSS(string=CSS_STYLE)],
)
print(f"✓ PDF saved: {PDF_FILE}  ({PDF_FILE.stat().st_size // 1024} KB)")
