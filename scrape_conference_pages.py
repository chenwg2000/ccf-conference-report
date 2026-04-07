#!/usr/bin/env python3
"""
Scrape conference program pages via Playwright to get
first-author institution data.
Each conference has a URL and a custom parser.
"""

import re, time, json, os
from playwright.sync_api import sync_playwright

OUTPUT = os.path.join(os.path.dirname(__file__), "conf_page_results.json")

# ── Chinese institution detector ─────────────────────────────────────────────
CN_KW = [
    "china", "chinese", "beijing", "shanghai", "tsinghua", "peking", "pku",
    "fudan", "zhejiang", "nanjing", "sjtu", "shanghai jiao tong",
    "wuhan", "harbin", "sun yat-sen", "sysu", "xi'an jiaotong",
    "huawei", "alibaba", "tencent", "bytedance", "baidu",
    "chinese academy", " cas,", " cas ", "ict cas",
    "iscas", "institute of software", "institute of computing technology",
    "national university of defense", "nudt",
    "university of science and technology of china", "ustc",
    "nankai", "tianjin", "chongqing", "tongji",
    "beihang", "buaa", "southeast university",
    "shenzhen", "guangzhou", "hangzhou", "hefei", "xiamen",
    "hong kong", "hkust", " hku ", "hku,", "cuhk", "cityu", "polyu",
    "chinese university of hong kong",
    "macau", "macao", "taiwan", "academia sinica",
]
def is_cn(s): return any(k in s.lower() for k in CN_KW) if s else False


# ── Generic approach: each conference gets a custom parse function ────────────
def parse_hpca_2025(text):
    """
    HPCA program: papers listed as "Title\nAuthors (Affil), ...\n..."
    Author line format: "Name (Affil), Name (Affil), ..."
    First author affiliation is in first parenthetical.
    """
    papers = []
    lines = [l.strip() for l in text.split('\n') if l.strip()]
    for i, line in enumerate(lines):
        # Author lines contain parentheses with institutions
        if '(' in line and ')' in line and i > 0:
            prev = lines[i-1]
            # Check if prev line looks like a paper title (no parens, reasonable length)
            if '(' not in prev and len(prev) > 15 and not prev.startswith('Session'):
                # Extract first affiliation (first set of parens)
                m = re.search(r'\(([^)]+)\)', line)
                if m:
                    affil = m.group(1)
                    papers.append({"title": prev[:60], "affil": affil, "cn": is_cn(affil)})
    return papers


def fetch_and_count(page, name, url, wait=3, parse_fn=None):
    """Fetch a conference page and parse affiliations."""
    print(f"\n  {name}: {url}")
    try:
        page.goto(url, timeout=35000)
        time.sleep(wait)
        text = page.inner_text("body")
        papers = parse_fn(text) if parse_fn else []
        cn = sum(1 for p in papers if p["cn"])
        total = len(papers)
        pct = round(cn / max(total, 1) * 100, 1)
        print(f"    → {total} papers, {cn} CN ({pct}%)")
        if total > 0:
            print("    CN papers:")
            for p in papers:
                if p["cn"]:
                    print(f"      ✓ {p['affil'][:60]}")
        return {"name": name, "total": total, "cn": cn, "pct": pct, "papers": papers}
    except Exception as e:
        print(f"    ERROR: {e}")
        return {"name": name, "total": 0, "cn": 0, "pct": 0, "error": str(e)}


# ── Conference-specific parsers ───────────────────────────────────────────────

def parse_generic_author_line(text, title_clue=None):
    """
    Generic parser: look for lines with '(Institution)' patterns
    following a title-like line.
    """
    papers = []
    lines = [l.strip() for l in text.split('\n') if l.strip()]
    for i, line in enumerate(lines):
        if '(' not in line or ')' not in line: continue
        if i == 0: continue
        prev = lines[i-1]
        # Skip nav/header lines
        if any(s in prev.lower() for s in ['session', 'chair:', 'break', 'keynote',
                                             'reception', 'pm', 'am', 'day ']):
            continue
        if '(' in prev or len(prev) < 15: continue
        m = re.search(r'\(([^)]{5,80})\)', line)
        if m:
            affil = m.group(1)
            # Filter out clearly non-institution strings
            if any(x in affil.lower() for x in ['http', 'www', '201', '202',
                                                   'room', 'floor']):
                continue
            papers.append({"title": prev[:60], "affil": affil, "cn": is_cn(affil)})
    return papers


def parse_hpca(text):    return parse_generic_author_line(text)
def parse_sc(text):      return parse_generic_author_line(text)
def parse_isca(text):    return parse_generic_author_line(text)
def parse_vis(text):     return parse_generic_author_line(text)
def parse_rtss(text):    return parse_generic_author_line(text)
def parse_hpdc(text):    return parse_generic_author_line(text)


def parse_sigmod(text):
    """SIGMOD paper list: 'Title\nAuthor1 (Inst), Author2 (Inst), ...'"""
    return parse_generic_author_line(text)


def parse_lics(text):
    """LICS accepted papers page."""
    papers = []
    lines = [l.strip() for l in text.split('\n') if l.strip()]
    for i, line in enumerate(lines):
        # LICS format: "Title. Author1, Author2, ..."
        if '(' in line and ')' in line:
            m = re.search(r'\(([^)]+)\)', line)
            if m:
                affil = m.group(1)
                papers.append({"title": line[:60], "affil": affil, "cn": is_cn(affil)})
    return papers


def parse_uist(text):
    """UIST has 'PaperTitle\nAuthor (Affil), Author (Affil)' format."""
    return parse_generic_author_line(text)


def parse_chi(text):
    """CHI has extensive program; look for author-institution patterns."""
    return parse_generic_author_line(text)


def parse_vldb(text):
    """VLDB program page."""
    return parse_generic_author_line(text)


def parse_sp(text):
    """S&P accepted papers - author lists with affiliations."""
    papers = []
    lines = [l.strip() for l in text.split('\n') if l.strip()]
    for i, line in enumerate(lines):
        if '(' in line and ')' in line and i > 0:
            prev = lines[i-1]
            if '(' not in prev and len(prev) > 10:
                m = re.search(r'\(([^)]+)\)', line)
                if m:
                    affil = m.group(1)
                    papers.append({"title": prev[:60], "affil": affil, "cn": is_cn(affil)})
    return papers


def parse_sigkdd(text):    return parse_generic_author_line(text)
def parse_sigir(text):     return parse_generic_author_line(text)
def parse_www(text):       return parse_generic_author_line(text)
def parse_ubicomp(text):   return parse_generic_author_line(text)


# ── Conference list with URLs and parsers ─────────────────────────────────────
CONFERENCES = [
    ("HPCA 2025",    "https://hpca-conf.org/2025/main-program/",           3, parse_hpca),
    ("ISCA 2025",    "https://iscaconf.org/isca2025/program.php",           3, parse_isca),
    ("SC 2024",      "https://sc24.supercomputing.org/program/papers/",      3, parse_sc),
    ("RTSS 2024",    "https://2024.rtss.org/conference-program/index.html", 3, parse_rtss),
    ("HPDC 2025",    "https://hpdc.sci.utah.edu/2025/program/",             3, parse_hpdc),
    ("LICS 2025",    "https://lics.siglog.org/lics25/accepted.php",         3, parse_lics),
    ("VR 2025",      "https://ieeevr.org/2025/program/papers/",             3, parse_vis),
    ("IEEE VIS 2024","https://ieeevis.org/year/2024/program/papers.html",   5, parse_vis),
    ("UIST 2024",    "https://uist.acm.org/2024/papers.html",               3, parse_uist),
    ("S&P 2025",     "https://sp2025.ieee-security.org/accepted-papers.html",3, parse_sp),
    ("SIGMOD 2025",  "https://2025.sigmod.org/sigmod_papers.shtml",         3, parse_sigmod),
    ("VLDB 2025",    "https://vldb.org/2025/?papers-research",              5, parse_vldb),
    ("SIGIR 2025",   "https://sigir2025.dei.unipd.it/accepted-papers.html", 5, parse_sigir),
    ("SIGKDD 2025",  "https://kdd2025.kdd.org/accepted-papers/",            3, parse_sigkdd),
    ("WWW 2025",     "https://www2025.thewebconf.org/research-tracks",       3, parse_www),
    ("UbiComp 2024", "https://www.ubicomp.org/ubicomp-iswc-2024/program/papers.html", 3, parse_ubicomp),
    ("CHI 2025",     "https://chi2025.acm.org/program/",                    5, parse_chi),
]


def main():
    existing = json.load(open(OUTPUT)) if os.path.exists(OUTPUT) else []
    done = {r["name"] for r in existing if r.get("total", 0) > 0 and not r.get("error")}
    print(f"Already done: {sorted(done)}")

    with sync_playwright() as pw:
        browser = pw.chromium.launch(headless=True)
        page = browser.new_page()
        page.set_extra_http_headers({"User-Agent":
            "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
            "Chrome/120.0.0.0 Safari/537.36"})

        for name, url, wait, parser in CONFERENCES:
            if name in done:
                print(f"  Skip {name}")
                continue
            result = fetch_and_count(page, name, url, wait, parser)
            existing = [r for r in existing if r.get("name") != name]
            existing.append(result)
            with open(OUTPUT, "w") as f:
                json.dump(existing, f, ensure_ascii=False, indent=2)

        browser.close()

    print("\n" + "="*60)
    print(f"{'Conference':<16} {'Total':>7} {'CN':>5} {'CN%':>7}")
    print("-"*35)
    for r in existing:
        if r.get("error"):
            print(f"{r['name']:<16} ERROR: {r['error'][:30]}")
        elif r.get("total", 0) == 0:
            print(f"{r['name']:<16} {'0':>7} {'0':>5} {'N/A':>7}")
        else:
            print(f"{r['name']:<16} {r['total']:>7} {r['cn']:>5} {r['pct']:>6.1f}%")


if __name__ == "__main__":
    main()
