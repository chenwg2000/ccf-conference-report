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
    size: A4 landscape;
    margin: 15mm 12mm 15mm 12mm;
    @bottom-center {
        content: counter(page) " / " counter(pages);
        font-size: 8pt;
        color: #888;
    }
}

* { box-sizing: border-box; }

body {
    font-family: "Noto Sans SC", "PingFang SC", "Microsoft YaHei", Arial, sans-serif;
    font-size: 10pt;
    line-height: 1.5;
    color: #222;
}

h1 {
    font-size: 17pt;
    font-weight: 700;
    color: #1a3a6b;
    border-bottom: 2.5px solid #1a3a6b;
    padding-bottom: 5px;
    margin-top: 0;
    margin-bottom: 8pt;
}

h2 {
    font-size: 12pt;
    font-weight: 700;
    color: #1a3a6b;
    border-left: 4px solid #1a3a6b;
    padding-left: 8px;
    margin-top: 18pt;
    margin-bottom: 6pt;
    page-break-after: avoid;
}

h3 {
    font-size: 10.5pt;
    font-weight: 700;
    color: #2c5f9e;
    margin-top: 12pt;
    margin-bottom: 4pt;
    page-break-after: avoid;
}

blockquote {
    background: #f0f4fb;
    border-left: 4px solid #2c5f9e;
    margin: 8pt 0;
    padding: 6pt 10pt;
    font-size: 8.5pt;
    color: #444;
    line-height: 1.5;
}

/* ── Main data tables (conference listings) ── */
table {
    width: 100%;
    border-collapse: collapse;
    font-size: 7.5pt;
    margin: 8pt 0;
    page-break-inside: auto;
    table-layout: fixed;
}

thead tr {
    background-color: #1a3a6b;
    color: white;
}

thead th {
    padding: 4pt 4pt;
    text-align: center;
    font-weight: 600;
    word-break: break-word;
    vertical-align: middle;
    line-height: 1.3;
}

tbody tr:nth-child(even) {
    background-color: #f2f6fc;
}

tbody td {
    padding: 3pt 4pt;
    border-bottom: 1px solid #e0e0e0;
    vertical-align: top;
    word-break: break-word;
    line-height: 1.35;
}

/* Column width hints for the main conference table (14 columns) */
/* 序号 | 简称 | 英文全称 | 中文名称 | 最近一届 | 举办地点 | 主办机构 | 参与人数 | 录用论文 | 投稿数 | 录用率 | 中国学者 | 占比 | 方法 */
col:nth-child(1)  { width: 3.5%; }   /* 序号 */
col:nth-child(2)  { width: 6%;   }   /* 简称 */
col:nth-child(3)  { width: 18%;  }   /* 英文全称 */
col:nth-child(4)  { width: 9%;   }   /* 中文名称 */
col:nth-child(5)  { width: 4.5%; }   /* 最近一届 */
col:nth-child(6)  { width: 8.5%; }   /* 举办地点 */
col:nth-child(7)  { width: 8.5%; }   /* 主办机构 */
col:nth-child(8)  { width: 5%;   }   /* 参与人数 */
col:nth-child(9)  { width: 5%;   }   /* 录用论文 */
col:nth-child(10) { width: 5%;   }   /* 投稿数 */
col:nth-child(11) { width: 5%;   }   /* 录用率 */
col:nth-child(12) { width: 5.5%; }   /* 中国学者 */
col:nth-child(13) { width: 4.5%; }   /* 占比 */
col:nth-child(14) { width: 3.5%; }   /* 方法 */

/* Summary / small tables — override to auto layout */
.summary-table table {
    table-layout: auto;
    font-size: 8.5pt;
}

tbody td:first-child {
    text-align: center;
    color: #666;
}

tbody td:nth-child(2) {
    font-weight: 600;
    color: #1a3a6b;
}

/* Numeric columns: center-align */
tbody td:nth-child(5),
tbody td:nth-child(8),
tbody td:nth-child(9),
tbody td:nth-child(10),
tbody td:nth-child(11),
tbody td:nth-child(12),
tbody td:nth-child(13),
tbody td:nth-child(14) {
    text-align: center;
}

/* Percentage highlight */
tbody td:nth-child(13) {
    font-weight: 600;
    color: #1a3a6b;
}

code {
    font-family: "Source Code Pro", "Courier New", monospace;
    background: #f5f5f5;
    padding: 1pt 2pt;
    border-radius: 2pt;
    font-size: 7.5pt;
}

hr {
    border: none;
    border-top: 1px solid #ccc;
    margin: 10pt 0;
}

p { margin: 5pt 0; }

ul, ol {
    margin: 5pt 0;
    padding-left: 18pt;
}

li { margin: 2pt 0; font-size: 9pt; }

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
