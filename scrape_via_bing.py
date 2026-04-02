#!/usr/bin/env python3
"""
For each CCF A-class conference:
  1. Bing-search for "[CONF] [YEAR] accepted papers program"
  2. Pick the most relevant official conference URL from results
  3. Navigate to that page (or a linked program/accepted-papers sub-page)
  4. Extract text and count first-author Chinese institution papers

Chinese institution detection: keyword match on affiliation text.
"""

import re, json, time, os
from playwright.sync_api import sync_playwright

RAW_DIR = "/home/nanogpt/prj/ccf-conference/raw_bing"
os.makedirs(RAW_DIR, exist_ok=True)

# ── Chinese institution patterns ──────────────────────────────────────────────
CN_PAT = re.compile(
    r'tsinghua|peking university|\bpku\b|beihang|\bbuaa\b|fudan|'
    r'zhejiang univ|\bzju\b|shanghai jiao tong|\bsjtu\b|'
    r'nanjing univ|\bnju\b|harbin inst(?:itute)?|\bhit\b|'
    r'univ(?:ersity)? of science and technology of china|\bustc\b|'
    r'beijing institute of technology|\bbit\b(?=.*china|.*beijing)|'
    r'sun yat.sen|\bsysu\b|wuhan univ|tongji univ|'
    r'huazhong univ|\bhust\b|southeast univ|'
    r'renmin univ|\bruc\b|nankai univ|tianjin univ|'
    r'shandong univ|jilin univ|northeastern univ(?:.*china)|'
    r'northwestern polytechnical|\bnwpu\b|xidian|xi.an jiaotong|\bxjtu\b|'
    r'sichuan univ|chongqing univ|central south univ|'
    r'dalian(?:.*tech(?:nology)?)|nat(?:ional)? univ(?:.*defense|\bof defense)|\bnudt\b|'
    r'chinese academy of sciences|inst(?:itute)? of computing technology|'
    r'inst(?:itute)? of information engineering|inst(?:itute)? of software.*chin|'
    r'shenzhen univ|southern univ.*sci(?:ence)?|\bsustech\b|'
    r'westlake univ|shanghaitech|'
    r'chinese univ(?:ersity)? of hong kong|\bcuhk\b|'
    r'hong kong univ(?:ersity)? of sci(?:ence)?|\bhkust\b|'
    r'univ(?:ersity)? of hong kong|city univ(?:.*hong kong)|hong kong polytechnic|'
    r'alibaba|alipay|ant group|ant financial|'
    r'tencent|baidu|bytedance|huawei|didi|meituan|\bjd(?:\.com| ai)\b|'
    r'sensetime|megvii|xiaomi|iflytek|hikvision|'
    r'kuaishou|\bkwai\b|zhipu|deepseek|moonshot|minimax|stepfun|'
    r'china mobile|china unicom|china telecom|zhongguancun|'
    r', china\b|\(china\b|china\)|china,\s*$|'
    r'hong kong|macau|macao|taiwan(?!.*disney)|'
    r'\bbeijing\b|\bshanghai\b|\bshenzhen\b|\bguangzhou\b|'
    r'\bhangzhou\b|\bchengdu\b|\bnanjing\b|\bwuhan\b|'
    r'xi.an\b|\btianjin\b|\bhefei\b|\bchongqing\b|\bchangsha\b|\bqingdao\b',
    re.IGNORECASE
)

def is_cn(text: str) -> bool:
    return bool(CN_PAT.search(text or ""))

# ── Conference list: (display_name, bing_query, year) ────────────────────────
CONFERENCES = [
    # Area 1
    ("PPoPP",         "PPoPP 2025 accepted papers program",             2025),
    ("FAST",          "USENIX FAST 2025 technical sessions",            2025),
    ("DAC",           "DAC 2025 Design Automation Conference accepted papers", 2025),
    ("HPCA",          "HPCA 2025 High Performance Computer Architecture program", 2025),
    ("MICRO",         "MICRO 2024 microarchitecture conference program", 2024),
    ("SC",            "SC24 supercomputing 2024 accepted papers",        2024),
    ("ASPLOS",        "ASPLOS 2025 accepted papers program",             2025),
    ("ISCA",          "ISCA 2025 computer architecture program",         2025),
    ("USENIX ATC",    "USENIX ATC 2025 annual technical conference technical sessions", 2025),
    ("EuroSys",       "EuroSys 2025 accepted papers",                   2025),
    ("HPDC",          "HPDC 2025 high performance parallel distributed program", 2025),
    # Area 2
    ("SIGCOMM",       "SIGCOMM 2025 ACM accepted papers",               2025),
    ("MobiCom",       "MobiCom 2024 ACM mobile computing accepted papers", 2024),
    ("INFOCOM",       "IEEE INFOCOM 2025 accepted paper list",           2025),
    ("NSDI",          "USENIX NSDI 2025 technical sessions",             2025),
    # Area 3
    ("CCS",           "ACM CCS 2024 computer communications security accepted papers", 2024),
    ("EUROCRYPT",     "EUROCRYPT 2025 IACR accepted papers",             2025),
    ("S&P",           "IEEE Symposium Security Privacy 2025 accepted papers Oakland", 2025),
    ("CRYPTO",        "CRYPTO 2024 IACR cryptology accepted papers",    2024),
    ("USENIX Security", "USENIX Security 2025 technical sessions",       2025),
    ("NDSS",          "NDSS 2025 network distributed system security accepted papers", 2025),
    # Area 4
    ("PLDI",          "PLDI 2025 programming language design implementation program", 2025),
    ("POPL",          "POPL 2025 principles programming languages program", 2025),
    ("FSE",           "FSE 2025 ESEC foundations software engineering accepted papers", 2025),
    ("SOSP",          "SOSP 2024 operating systems principles program",  2024),
    ("OOPSLA",        "OOPSLA 2024 object oriented programming accepted papers", 2024),
    ("ASE",           "ASE 2024 automated software engineering accepted papers", 2024),
    ("ICSE",          "ICSE 2025 international conference software engineering accepted", 2025),
    ("ISSTA",         "ISSTA 2025 software testing analysis accepted papers", 2025),
    ("OSDI",          "USENIX OSDI 2024 operating systems design implementation", 2024),
    ("FM",            "FM 2024 formal methods international symposium program", 2024),
    # Area 5
    ("SIGMOD",        "SIGMOD 2025 ACM database accepted papers",        2025),
    ("SIGKDD",        "KDD 2025 knowledge discovery data mining accepted papers", 2025),
    ("ICDE",          "ICDE 2025 IEEE data engineering accepted papers", 2025),
    ("SIGIR",         "SIGIR 2025 information retrieval accepted papers", 2025),
    ("VLDB",          "VLDB 2025 very large data bases proceedings",     2025),
    # Area 6
    ("STOC",          "STOC 2025 theory computing accepted papers",      2025),
    ("SODA",          "SODA 2025 ACM SIAM discrete algorithms accepted papers", 2025),
    ("CAV",           "CAV 2025 computer aided verification accepted papers", 2025),
    ("FOCS",          "FOCS 2024 IEEE foundations computer science accepted papers", 2024),
    ("LICS",          "LICS 2025 logic computer science accepted papers", 2025),
    # Area 7
    ("ACM MM",        "ACM Multimedia MM 2024 accepted papers",          2024),
    ("SIGGRAPH",      "SIGGRAPH 2025 ACM computer graphics technical papers", 2025),
    ("VR",            "IEEE VR 2025 virtual reality conference program", 2025),
    ("IEEE VIS",      "IEEE VIS 2024 visualization accepted papers",     2024),
    # Area 8
    ("AAAI",          "AAAI 2025 artificial intelligence accepted papers program", 2025),
    ("NeurIPS",       "NeurIPS 2024 neural information processing accepted papers", 2024),
    ("ACL",           "ACL 2025 computational linguistics accepted papers", 2025),
    ("CVPR",          "CVPR 2025 computer vision pattern recognition accepted papers", 2025),
    ("ICCV",          "ICCV 2023 computer vision accepted papers",       2023),
    ("ICML",          "ICML 2025 machine learning accepted papers",      2025),
    ("ICLR",          "ICLR 2025 learning representations accepted papers", 2025),
    # Area 9
    ("CSCW",          "CSCW 2024 ACM computer supported cooperative work accepted papers", 2024),
    ("CHI",           "CHI 2025 ACM human factors computing accepted papers", 2025),
    ("UbiComp",       "UbiComp ISWC 2024 pervasive ubiquitous computing program", 2024),
    ("UIST",          "UIST 2024 ACM user interface software technology program", 2024),
    # Area 10
    ("WWW",           "WWW 2025 The Web Conference accepted papers",     2025),
    ("RTSS",          "RTSS 2024 IEEE real-time systems symposium accepted papers", 2024),
]

# ── Bing search ───────────────────────────────────────────────────────────────
def bing_search(page, query: str) -> list[str]:
    """Return top-5 result URLs from Bing."""
    page.goto(f"https://www.bing.com/search?q={query.replace(' ', '+')}&count=10",
              wait_until="domcontentloaded", timeout=20000)
    page.wait_for_timeout(1500)

    urls = []
    # Bing result links — use h2 a (most reliable across Bing layouts)
    seen = set()
    for a in page.query_selector_all("h2 a, .b_algo a"):
        href = a.get_attribute("href") or ""
        if (href.startswith("http")
                and "bing.com" not in href
                and "microsoft.com" not in href
                and href not in seen):
            seen.add(href)
            urls.append(href)
        if len(urls) >= 8:
            break
    return urls


# ── Sub-page finder ───────────────────────────────────────────────────────────
PROGRAM_LINK_TEXTS = re.compile(
    r'accepted papers?|technical sessions?|program|papers?|proceedings?|schedule',
    re.IGNORECASE
)
PROGRAM_LINK_HREFS = re.compile(
    r'accept|papers?|program|session|proceedings?|schedule',
    re.IGNORECASE
)

def find_program_subpage(page, base_url: str) -> str | None:
    """Try to find an 'accepted papers' or 'program' sub-page link on the conference homepage."""
    try:
        page.goto(base_url, wait_until="domcontentloaded", timeout=20000)
        page.wait_for_timeout(2000)
    except Exception:
        return None

    for a in page.query_selector_all("a[href]"):
        try:
            text = (a.inner_text() or "").strip()
            href = a.get_attribute("href") or ""
            if (PROGRAM_LINK_TEXTS.search(text) or PROGRAM_LINK_HREFS.search(href)):
                if href.startswith("/"):
                    from urllib.parse import urljoin
                    href = urljoin(base_url, href)
                if href.startswith("http") and base_url.split("/")[2] in href:
                    return href
        except Exception:
            continue
    return None


# ── Content parser ────────────────────────────────────────────────────────────
INST_KW = re.compile(
    r'university|universit[eéyä]|univ\b|institute|institution|laboratory|lab\b|'
    r'college|school of|department|faculty|'
    r'research center|research lab|r&d|'
    r'company|corporation|corp\b|inc\b|ltd\b|gmbh|s\.a\.|'
    r'google|microsoft|meta\b|amazon|apple|ibm|intel|nvidia|amd|'
    r'alibaba|tencent|baidu|bytedance|huawei|sensetime|megvii',
    re.IGNORECASE
)

def extract_chinese_stats(content: str) -> tuple[int, int]:
    """
    Parse free-form conference program text.
    Returns (total_papers_with_affiliation, cn_first_author_count).

    Strategy: scan for paragraph/line blocks that contain an institution mention.
    The first institution in each "paper block" is treated as the first author's affil.
    """
    total = 0
    cn = 0

    # Split into logical blocks (separated by blank lines or '---')
    blocks = re.split(r'\n{2,}|(?:^|\n)[-─═]{3,}', content)

    for block in blocks:
        block = block.strip()
        if not block or len(block) < 20:
            continue

        lines = [l.strip() for l in block.split('\n') if l.strip()]

        # Find first line that looks like an affiliation
        first_affil = None
        for line in lines:
            if INST_KW.search(line) and len(line) < 200:
                first_affil = line
                break

        if first_affil:
            total += 1
            if is_cn(first_affil) or is_cn(block[:400]):
                cn += 1

    # Fallback: if we found < 5 blocks, try line-by-line with parenthesized affiliations
    if total < 5:
        total2, cn2 = 0, 0
        for line in content.split('\n'):
            line = line.strip()
            # "(Institution, Country)" pattern
            affils = re.findall(r'\(([^)]{5,100})\)', line)
            for affil in affils:
                if INST_KW.search(affil):
                    total2 += 1
                    if is_cn(affil):
                        cn2 += 1
                    break  # only first affiliation per line
        if total2 > total:
            total, cn = total2, cn2

    return total, cn


def is_official_conf_url(url: str, conf_name: str) -> bool:
    """Rough check: prefer conference-specific domains, not generic aggregators."""
    bad = ["dblp.org", "scholar.google", "semanticscholar", "arxiv.org",
           "wikipedia", "youtube", "linkedin", "twitter", "x.com",
           "openreview.net", "acm.org/doi", "ieee.org/document",
           "dl.acm.org/doi/10", "ieeexplore.ieee.org/document"]
    return not any(b in url.lower() for b in bad)


# ── Main ──────────────────────────────────────────────────────────────────────
def process_conference(browser, name: str, query: str, year: int) -> dict:
    ctx = browser.new_context(
        user_agent="Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
                   "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
        viewport={"width": 1280, "height": 900},
    )
    search_page = ctx.new_page()

    try:
        # 1. Bing search
        print(f"    Bing: {query[:60]}", end="", flush=True)
        urls = bing_search(search_page, query)
        if not urls:
            print(" → no results")
            return {"name": name, "year": year, "error": "no Bing results"}
        print(f" → {len(urls)} results")

        # 2. Try each URL until we find a useful program page
        content = ""
        used_url = ""
        for url in urls:
            if not is_official_conf_url(url, name):
                continue
            print(f"    → trying {url[:70]}", end="", flush=True)
            try:
                search_page.goto(url, wait_until="domcontentloaded", timeout=20000)
                search_page.wait_for_timeout(2500)
                page_text = search_page.inner_text("body")
                print(f" ({len(page_text)} chars)", end="")

                # Check if this page already has useful content
                if len(page_text) > 5000 and INST_KW.search(page_text):
                    content = page_text
                    used_url = url
                    print(" ✓ has affiliations")
                    break

                # Otherwise look for a sub-page
                sub = find_program_subpage(search_page, url)
                if sub and sub != url:
                    print(f"\n      sub-page: {sub[:70]}", end="", flush=True)
                    try:
                        search_page.goto(sub, wait_until="domcontentloaded", timeout=20000)
                        search_page.wait_for_timeout(2500)
                        sub_text = search_page.inner_text("body")
                        print(f" ({len(sub_text)} chars)", end="")
                        if len(sub_text) > 3000 and INST_KW.search(sub_text):
                            content = sub_text
                            used_url = sub
                            print(" ✓")
                            break
                        else:
                            print(" (no affiliations)")
                    except Exception as e2:
                        print(f" err: {e2}")
                else:
                    print(" (no sub-page found)")

            except Exception as e:
                print(f" err: {e}")
                continue

        if not content:
            print(f"    [WARNING] no useful page found for {name}")
            return {"name": name, "year": year, "url": "", "error": "no content", "total": 0, "cn": 0}

        # 3. Save raw content
        safe_name = name.replace(' ', '_').replace('/', '_').replace('&', 'and')
        raw_path = os.path.join(RAW_DIR, f"{safe_name}_{year}.txt")
        with open(raw_path, "w", encoding="utf-8") as f:
            f.write(f"URL: {used_url}\n\n{content[:80000]}")

        # 4. Extract stats
        total, cn = extract_chinese_stats(content)
        pct = round(cn / max(total, 1) * 100, 1)
        print(f"    RESULT: {total} affil-blocks, {cn} CN ({pct}%)")

        return {
            "name": name, "year": year, "url": used_url,
            "total": total, "cn": cn, "pct": pct, "error": None,
        }

    finally:
        ctx.close()


def main():
    results = []
    n = len(CONFERENCES)
    print(f"Processing {n} conferences via Bing → program page → affiliation count")
    print("=" * 80)

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)

        for i, (name, query, year) in enumerate(CONFERENCES):
            print(f"\n[{i+1}/{n}] {name} ({year})")

            # Check cache first
            safe_name = name.replace(' ', '_').replace('/', '_').replace('&', 'and')
            raw_path = os.path.join(RAW_DIR, f"{safe_name}_{year}.txt")
            if os.path.exists(raw_path) and os.path.getsize(raw_path) > 3000:
                print(f"    [cached] reading {raw_path}")
                with open(raw_path) as f:
                    content = f.read()
                total, cn = extract_chinese_stats(content)
                pct = round(cn / max(total, 1) * 100, 1)
                url_line = content.split('\n')[0].replace("URL: ", "")
                print(f"    RESULT: {total} blocks, {cn} CN ({pct}%)")
                results.append({"name": name, "year": year, "url": url_line,
                                 "total": total, "cn": cn, "pct": pct, "error": None})
            else:
                result = process_conference(browser, name, query, year)
                results.append(result)

            time.sleep(1.5)  # polite delay between conferences

        browser.close()

    # ── Summary ──────────────────────────────────────────────────────────────
    print("\n" + "=" * 80)
    print(f"{'Conference':<18} {'Year':<6} {'Total':<8} {'CN':<8} {'CN%':<8} {'URL':<50}")
    print("-" * 98)
    for r in results:
        if r.get("error") and r.get("total", 0) == 0:
            print(f"{r['name']:<18} {r['year']:<6} {'ERR':<8} {'-':<8} {'-':<8} {r.get('error','')}")
        else:
            url_short = (r.get("url") or "")[:48]
            print(f"{r['name']:<18} {r['year']:<6} {r.get('total',0):<8} "
                  f"{r.get('cn',0):<8} {r.get('pct',0):.1f}%    {url_short}")

    out = "/home/nanogpt/prj/ccf-conference/bing_results.json"
    with open(out, "w", encoding="utf-8") as f:
        json.dump(results, f, ensure_ascii=False, indent=2)
    print(f"\nSaved → {out}")


if __name__ == "__main__":
    main()
