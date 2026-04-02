#!/usr/bin/env python3
"""
1. Parse scraped raw text files to count Chinese first-author papers.
2. Retry failed conferences with alternative (non-ACM-DL) URLs.
"""

import re
import json
import time
import os
from playwright.sync_api import sync_playwright

RAW_DIR = "/home/nanogpt/prj/ccf-conference/raw"
RESULTS_FILE = "/home/nanogpt/prj/ccf-conference/browser_scrape_results.json"

# Chinese institution keywords (institution names, cities, companies)
CN_KEYWORDS_INST = [
    # Explicit country marker
    r", china\b", r"\(china\b", r",\s*china\s*\)", r"china\s*\)",
    # Hong Kong / Macao / Taiwan (ROC) - included as Chinese institutions
    r"hong kong", r"macau", r"macao",
    # Top mainland universities
    r"tsinghua", r"peking university", r"\bpku\b", r"beihang", r"\bbuaa\b",
    r"fudan", r"zhejiang university", r"\bzju\b",
    r"shanghai jiao tong", r"\bsjtu\b",
    r"nanjing university", r"\bnju\b",
    r"harbin institute", r"\bhit\b",
    r"university of science and technology of china", r"\bustc\b",
    r"beijing institute of technology",
    r"sun yat.sen", r"\bsysu\b",
    r"wuhan university", r"tongji",
    r"huazhong university", r"\bhust\b",
    r"southeast university",
    r"renmin university", r"\bruc\b",
    r"nankai", r"tianjin university",
    r"shandong university", r"jilin university",
    r"northeastern university.*china",  # avoid US northeastern
    r"northwestern polytechnical",
    r"\bnwpu\b", r"xidian",
    r"xi.an jiaotong", r"\bxjtu\b",
    r"sichuan university", r"chongqing university",
    r"central south university",
    r"dalian.*technology", r"dalian university",
    r"national university of defense technology", r"\bnudt\b",
    r"chinese academy of sciences", r"\bcas\b.*china", r"institute of computing technology",
    r"institute of information engineering",
    r"institute of software.*chinese",
    r"shenzhen university",
    r"southern university of science", r"\bsustech\b",
    r"westlake university", r"shanghaitech",
    r"chinese university of hong kong", r"\bcuhk\b",
    r"hong kong university of science", r"\bhkust\b",
    r"university of hong kong",
    r"city university of hong kong",
    r"hong kong polytechnic",
    r"university of macau",
    # Chinese cities (as part of institution names)
    r"beijing\b", r"shanghai\b", r"shenzhen\b", r"guangzhou\b",
    r"hangzhou\b", r"chengdu\b", r"nanjing\b", r"wuhan\b",
    r"xi'an\b", r"xian\b", r"tianjin\b", r"hefei\b", r"chongqing\b",
    r"qingdao\b", r"changsha\b", r"suzhou\b", r"zhengzhou\b",
    # Chinese tech companies
    r"alibaba", r"alipay", r"ant group", r"ant financial",
    r"tencent", r"baidu", r"\bbytedance\b",
    r"huawei", r"didi", r"meituan", r"\bjd\.com\b", r"\bjd ai\b",
    r"netease", r"sensetime", r"megvii",
    r"xiaomi", r"oppo\b", r"vivo\b",
    r"iflytek", r"hikvision", r"dahua",
    r"kuaishou", r"\bkwai\b",
    r"zhipu", r"moonshot", r"deepseek", r"minimax", r"stepfun",
    # Generic
    r"china mobile", r"china unicom", r"china telecom",
    r"zhongguancun",
]

CN_PATTERN = re.compile(
    '|'.join(CN_KEYWORDS_INST),
    re.IGNORECASE
)


def is_cn_institution(text: str) -> bool:
    return bool(CN_PATTERN.search(text))


# ─── Parsers for each conference format ──────────────────────────────────────

def parse_usenix(content: str) -> list[dict]:
    """
    USENIX format:
      Paper Title
      Author1, Author2, Institution1; Author3, Institution2
      AVAILABLE MEDIA  (or blank line)
    Returns list of {title, first_author_affil}
    """
    papers = []
    lines = [l.strip() for l in content.split('\n')]

    i = 0
    while i < len(lines) - 1:
        title_line = lines[i]
        author_line = lines[i + 1] if i + 1 < len(lines) else ""

        # Author line contains semicolons and institution names
        # Title line is non-empty, not a nav item
        if (len(title_line) > 20 and
                not title_line.startswith(('Session', 'Track', 'Chair', 'Monday',
                                           'Tuesday', 'Wednesday', 'Thursday',
                                           'Friday', 'am', 'pm', 'Coffee', 'Break',
                                           'AVAILABLE', 'Full', 'Attendee',
                                           'Proceedings', 'USENIX')) and
                ';' in author_line or ',' in author_line):

            # First group before first semicolon = first author(s) + their institution
            first_group = author_line.split(';')[0]
            # Institution is after " and " or after last comma before an institution word
            # Pattern: "Name1, Name2, Institution" or "Name1 and Name2, Institution"
            parts = first_group.split(',')
            if len(parts) >= 2:
                # Last part after comma is likely the institution
                affil = parts[-1].strip()
                if len(affil) > 3:
                    papers.append({
                        "title": title_line,
                        "first_affil": affil,
                        "is_cn": is_cn_institution(affil) or is_cn_institution(first_group),
                    })
        i += 1

    return papers


def parse_infocom(content: str) -> list[dict]:
    """
    INFOCOM format:
      Paper Title

      Author1 and Author2 (Institution1, Country); Author3 (Institution2)
    """
    papers = []
    # Split into blocks by double newlines
    blocks = re.split(r'\n{2,}', content)

    for j, block in enumerate(blocks):
        block = block.strip()
        if not block:
            continue
        # Author block contains parentheses with institutions
        if '(' in block and ')' in block and j > 0:
            # The preceding block might be the title
            title = blocks[j - 1].strip() if j > 0 else ""
            # Extract first author's institution: first (...)
            m = re.search(r'\(([^)]+)\)', block)
            if m:
                affil = m.group(1)
                papers.append({
                    "title": title,
                    "first_affil": affil,
                    "is_cn": is_cn_institution(affil) or is_cn_institution(block),
                })

    return papers


def parse_ccs(content: str) -> list[dict]:
    """
    CCS format: author per line with (Institution) in parens
      Paper Title    Author1 (Inst1)
      Author2 (Inst2)
    """
    papers = []
    lines = content.split('\n')

    i = 0
    while i < len(lines):
        line = lines[i].strip()
        # Tab-separated: "Title\tFirst Author (Institution)"
        if '\t' in line:
            parts = line.split('\t')
            if len(parts) >= 2:
                title = parts[0].strip()
                author_part = parts[1].strip()
                m = re.search(r'\(([^)]+)\)', author_part)
                if m:
                    affil = m.group(1)
                    papers.append({
                        "title": title,
                        "first_affil": affil,
                        "is_cn": is_cn_institution(affil),
                    })
        i += 1

    # Also try: "Name (Institution)\n" blocks
    for line in lines:
        line = line.strip()
        m = re.match(r'^([^(]+)\(([^)]{5,80})\)\s*$', line)
        if m and len(m.group(2)) > 5:
            papers.append({
                "title": "",
                "first_affil": m.group(2),
                "is_cn": is_cn_institution(m.group(2)),
            })

    return papers


def parse_generic_with_affiliations(content: str) -> list[dict]:
    """
    Generic parser: find all institution mentions and count Chinese ones.
    For the purpose of counting, we look for patterns like:
      (Institution, Country)
      Author (Institution)
      Name - Institution
    and try to associate with "first author" by ordering.
    """
    papers = []
    lines = content.split('\n')

    # Look for blocks: title line followed by author(s) with affiliations
    i = 0
    while i < len(lines):
        line = lines[i].strip()
        if not line:
            i += 1
            continue

        # Check next few lines for affiliations
        context = ' '.join(lines[i:i+5])

        # Pattern: "Author (Institution, Country)"
        m = re.search(r'\(([^)]{5,100}(?:university|institute|lab|school|research|corp|inc|ltd|group|china|usa|uk|germany|france|japan|korea|singapore|australia|canada)[^)]{0,50})\)',
                      context, re.IGNORECASE)
        if m:
            affil = m.group(1)
            papers.append({
                "title": line[:100],
                "first_affil": affil,
                "is_cn": is_cn_institution(affil),
            })
            i += 3
            continue
        i += 1

    return papers


def parse_sigplan(content: str) -> list[dict]:
    """
    sigplan.org conference pages:
    Paper entries with expandable details.
    Format: title, then authors listed with institutions.
    """
    # Look for "(Institution)" patterns
    papers = []
    lines = content.split('\n')
    i = 0
    while i < len(lines):
        line = lines[i].strip()
        # Institution line follows author name line
        if len(line) > 5:
            m = re.match(r'^(.{3,60}),\s+(.{5,80}(?:university|institute|lab|labs|research|college|inc|ltd|corp|company|group|school|academy)[^,\n]{0,60})$',
                         line, re.IGNORECASE)
            if m:
                affil = m.group(2)
                papers.append({
                    "title": "",
                    "first_affil": affil,
                    "is_cn": is_cn_institution(affil),
                })
        i += 1
    return papers


def parse_stoc_focs(content: str) -> list[dict]:
    """
    STOC/FOCS/theory conference pages: papers listed with author names.
    Institutions listed separately or as "(Inst)".
    """
    papers = []
    for line in content.split('\n'):
        line = line.strip()
        # "(Institution)" pattern
        matches = re.findall(r'\(([^)]{5,100})\)', line)
        for m in matches:
            if any(kw in m.lower() for kw in ['university', 'institute', 'school',
                                                'college', 'lab', 'research', 'weizmann',
                                                'eth', 'epfl', 'inria', 'mit', 'mpi']):
                papers.append({
                    "title": "",
                    "first_affil": m,
                    "is_cn": is_cn_institution(m),
                })
                break  # only first affiliation per line
    return papers


# Map strategy to parser
PARSERS = {
    "usenix": parse_usenix,
    "infocom_style": parse_infocom,
    "ccs_style": parse_ccs,
    "sigplan": parse_sigplan,
    "theory": parse_stoc_focs,
    "generic": parse_generic_with_affiliations,
}

# Per-conference parser assignment and counting approach
CONF_PARSERS = {
    # USENIX-style (author, institution; format)
    "FAST": "usenix",
    "USENIX ATC": "usenix",
    "NSDI": "usenix",
    "USENIX Security": "usenix",
    "OSDI": "usenix",
    # INFOCOM-style (parenthesized affiliations)
    "INFOCOM": "infocom_style",
    "VR": "infocom_style",
    # CCS-style (tab-separated with parens)
    "CCS": "ccs_style",
    "NDSS": "ccs_style",
    # Theory (short affiliation lists)
    "STOC": "theory",
    "FOCS": "theory",
    "CAV": "theory",
    "LICS": "theory",
    # Generic
    "PLDI": "sigplan",
    "POPL": "sigplan",
}


def analyze_raw_file(name: str, content: str) -> dict:
    """Parse raw content and count Chinese first-author papers."""
    strategy = CONF_PARSERS.get(name, "generic")
    parser = PARSERS[strategy]

    papers = parser(content)

    total = len(papers)
    cn_count = sum(1 for p in papers if p.get("is_cn", False))

    # Fallback: if we got < 10 papers, try generic parser
    if total < 10:
        papers2 = parse_generic_with_affiliations(content)
        if len(papers2) > total:
            total = len(papers2)
            cn_count = sum(1 for p in papers2 if p.get("is_cn", False))

    return {
        "strategy": strategy,
        "total_parsed": total,
        "cn_first_affil": cn_count,
        "cn_pct": round(cn_count / max(total, 1) * 100, 1),
        "sample": [p for p in papers[:3] if p.get("is_cn")],
    }


# ─── Retry for failed ACM DL conferences ─────────────────────────────────────

RETRY_URLS = {
    "PPoPP":    "https://ppopp25.sigplan.org/track/PPoPP-2025-papers",
    "DAC":      "https://dl.acm.org/doi/proceedings/10.5555/3778334",  # try with longer timeout
    "MICRO":    "https://microarch.org/micro57/",
    "ASPLOS":   "https://www.asplos-conference.org/asplos2025/program.html",
    "ISCA":     "https://iscaconf.org/isca2025/program.php",
    "EuroSys":  "https://2025.eurosys.org/accepted-papers.html",
    "HPDC":     "https://hpdc.sci.utah.edu/2025/program",
    "SIGCOMM":  "https://conferences.sigcomm.org/sigcomm/2025/accepted-papers/",
    "MobiCom":  "https://www.sigmobile.org/mobicom/2024/accepted.html",
    "CRYPTO":   "https://crypto.iacr.org/2024/acceptedpapers.php",
    "SOSP":     "https://sigops.org/s/conferences/sosp/2024/program.html",
    "ASE":      "https://conf.researchr.org/home/ase-2024",
    "ICSE":     "https://conf.researchr.org/track/icse-2025/icse-2025-research-track",
    "SIGKDD":   "https://kdd2025.kdd.org/accepted-papers-research-track/",
    "SODA":     "https://epubs.siam.org/toc/sjcomp/2025/54/1",
    "ACM MM":   "https://2024.acmmm.org/accepted-list",
    "SIGGRAPH": "https://s2025.siggraph.org/program/technical-papers/",
    "IEEE VIS": "https://ieeevis.org/year/2024/program/papers.html",
    "ACL":      "https://aclanthology.org/venues/acl/",
    "CSCW":     "https://cscw.acm.org/2024/index.php/accepted-papers/",
    "CHI":      "https://chi2025.acm.org/",
    "UbiComp":  "https://www.ubicomp.org/ubicomp-iswc-2024/program/",
    "UIST":     "https://uist.acm.org/2024/program/",
    "WWW":      "https://www2025.thewebconf.org/",
}


def scrape_page(browser, url: str, timeout_ms: int = 45000) -> str:
    context = browser.new_context(
        user_agent="Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
    )
    page = context.new_page()
    try:
        # Use domcontentloaded instead of networkidle for faster loading
        page.goto(url, wait_until="domcontentloaded", timeout=timeout_ms)
        page.wait_for_timeout(3000)
        content = page.inner_text("body")
        return content
    except Exception as e:
        return f"ERROR: {e}"
    finally:
        context.close()


def main():
    # ── Step 1: Parse existing raw files ────────────────────────────────────
    print("=" * 80)
    print("STEP 1: Parsing existing raw files")
    print("=" * 80)

    parse_results = {}
    raw_files = [f for f in os.listdir(RAW_DIR) if f.endswith('.txt')]

    for fname in sorted(raw_files):
        conf_name = fname.replace('.txt', '')
        # Map filename back to conference name
        # filename format: CONF_NAME_YEAR.txt
        # e.g., USENIX_ATC_2025.txt -> USENIX ATC
        parts = conf_name.rsplit('_', 1)  # split on last underscore (year)
        display_name = parts[0].replace('_', ' ')

        with open(os.path.join(RAW_DIR, fname), encoding='utf-8') as f:
            content = f.read()

        result = analyze_raw_file(display_name, content)
        parse_results[display_name] = result
        print(f"  {display_name:20}: {result['total_parsed']:4} blocks, "
              f"{result['cn_first_affil']:4} CN ({result['cn_pct']:.1f}%)"
              f"  [{result['strategy']}]")

    # ── Step 2: Retry failed conferences ────────────────────────────────────
    print("\n" + "=" * 80)
    print("STEP 2: Scraping failed conferences with alternative URLs")
    print("=" * 80)

    retry_results = {}
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)

        for name, url in RETRY_URLS.items():
            raw_path = os.path.join(RAW_DIR, f"{name.replace(' ', '_').replace('/', '_')}_retry.txt")
            if os.path.exists(raw_path):
                print(f"  {name:15}: [cached] reading existing retry file")
                with open(raw_path) as f:
                    content = f.read()
            else:
                print(f"  {name:15}: fetching {url[:60]}...", end="", flush=True)
                content = scrape_page(browser, url)
                if content.startswith("ERROR"):
                    print(f" {content}")
                    retry_results[name] = {"error": content}
                    continue
                with open(raw_path, 'w', encoding='utf-8') as f:
                    f.write(content[:60000])
                print(f" {len(content)} chars")

            result = analyze_raw_file(name, content)
            retry_results[name] = result
            print(f"    -> {result['total_parsed']} blocks, {result['cn_first_affil']} CN "
                  f"({result['cn_pct']:.1f}%) [{result['strategy']}]")
            time.sleep(1)

        browser.close()

    # ── Step 3: Combined summary ─────────────────────────────────────────────
    print("\n" + "=" * 80)
    print("COMBINED RESULTS")
    print("=" * 80)
    print(f"{'Conference':<18} {'Source':<10} {'Parsed':<8} {'CN First':<10} {'CN%':<7}")
    print("-" * 55)

    all_results = {}
    for name, r in {**parse_results, **retry_results}.items():
        if r.get("error"):
            print(f"{name:<18} {'retry':<10} {'ERR':<8}")
            continue
        source = "retry" if name in retry_results else "cached"
        print(f"{name:<18} {source:<10} {r['total_parsed']:<8} "
              f"{r['cn_first_affil']:<10} {r['cn_pct']:.1f}%")
        all_results[name] = r

    out = "/home/nanogpt/prj/ccf-conference/parsed_results.json"
    with open(out, "w", encoding="utf-8") as f:
        json.dump(all_results, f, ensure_ascii=False, indent=2)
    print(f"\nSaved to {out}")


if __name__ == "__main__":
    main()
