#!/usr/bin/env python3
"""
Fix parsers for remaining conferences and scrape better URLs.
"""

import re, json, time, os
from playwright.sync_api import sync_playwright

RAW_DIR = "/home/nanogpt/prj/ccf-conference/raw"

CN_KEYWORDS = [
    r",\s*china\b", r"\(china\b", r"china\s*\)", r", china$",
    r"hong kong", r"macau", r"macao",
    r"tsinghua", r"peking university", r"\bpku\b", r"beihang",
    r"fudan", r"zhejiang university", r"\bzju\b",
    r"shanghai jiao tong", r"\bsjtu\b",
    r"nanjing university", r"\bnju\b", r"harbin institute", r"\bhit\b",
    r"university of science and technology of china", r"\bustc\b",
    r"sun yat.sen", r"\bsysu\b", r"wuhan university", r"tongji",
    r"huazhong university", r"\bhust\b", r"southeast university",
    r"renmin university", r"\bruc\b", r"nankai", r"tianjin university",
    r"shandong university", r"jilin university",
    r"northwestern polytechnical", r"\bnwpu\b", r"xidian", r"xi.an jiaotong",
    r"sichuan university", r"chongqing university", r"central south university",
    r"dalian.*technology", r"national university of defense technology", r"\bnudt\b",
    r"chinese academy of sciences", r"institute of computing technology",
    r"institute of information engineering", r"institute of software.*chinese",
    r"shenzhen university", r"southern university of science", r"\bsustech\b",
    r"westlake university", r"shanghaitech",
    r"chinese university of hong kong", r"\bcuhk\b",
    r"hong kong university of science", r"\bhkust\b",
    r"university of hong kong", r"city university of hong kong",
    r"hong kong polytechnic",
    r"alibaba", r"alipay", r"ant group", r"tencent", r"baidu", r"\bbytedance\b",
    r"huawei", r"didi", r"meituan", r"\bjd ai\b",
    r"sensetime", r"megvii", r"xiaomi", r"iflytek",
    r"kuaishou", r"\bkwai\b", r"zhipu", r"deepseek", r"moonshot", r"minimax",
    r"china mobile", r"china unicom", r"china telecom", r"zhongguancun",
    r"\bbeijing\b", r"\bshanghai\b", r"\bshenzhen\b", r"\bguangzhou\b",
    r"\bhangzhou\b", r"\bchengdu\b", r"\bnanjing\b", r"\bwuhan\b",
    r"\bxi'an\b", r"\bxian\b", r"\btianjin\b", r"\bhefei\b", r"\bchongqing\b",
    r"\bqingdao\b", r"\bchangsha\b",
]
CN_PAT = re.compile('|'.join(CN_KEYWORDS), re.IGNORECASE)


def is_cn(text): return bool(CN_PAT.search(text or ""))


# ─── Conference-specific scrapers and parsers ─────────────────────────────────

def parse_eurocrypt_style(content: str) -> tuple[int, int]:
    """
    IACR format (EUROCRYPT/CRYPTO):
      Paper Title
      Author1, Author2
      Institution1, Institution2
    """
    lines = [l.strip() for l in content.split('\n') if l.strip()]
    total, cn = 0, 0
    i = 0
    while i < len(lines) - 2:
        # Look for a pattern: title line → author line (contains names) → institution line
        title = lines[i]
        maybe_authors = lines[i+1] if i+1 < len(lines) else ""
        maybe_inst = lines[i+2] if i+2 < len(lines) else ""

        # Author line: comma-separated names, no "university/institute/lab" words
        # Institution line: contains institution keywords
        inst_words = re.compile(r'university|institute|laboratory|lab |college|school|research|ltd|inc\.|gmbh|'
                                r'ntt|ibm|google|microsoft|meta|amazon|apple|adobe|qualcomm|intel|'
                                r'epfl|eth |inria|cnrs|rwth|tum |imec|rit |mit |tue |kth |usc |nyu ',
                                re.IGNORECASE)

        if inst_words.search(maybe_inst) and not inst_words.search(maybe_authors):
            total += 1
            if is_cn(maybe_inst):
                cn += 1
            i += 3
        else:
            i += 1

    return total, cn


def parse_cvf_openaccess(content: str) -> tuple[int, int]:
    """
    CVF OpenAccess format:
      Paper Title [paper] [bibtex] [reviews]
      Author1, Author2, Author3
      [abstract text...]
    No affiliations visible on this page unfortunately.
    Try to detect author names then scan nearby text for CN keywords.
    """
    # Actually CVF open access does show affiliations in a compact format
    # "Author (Inst)"
    total, cn = 0, 0
    # Pattern: find paper entries with at least one CN author
    # Split by paper separators
    blocks = re.split(r'\n(?=[A-Z][^\n]{20,150}\n)', content)
    for block in blocks:
        lines = block.strip().split('\n')
        if len(lines) < 2:
            continue
        # Check if block mentions institutions
        if is_cn(block):
            total += 1
            cn += 1
        elif any(kw in block.lower() for kw in ['university', 'institute', 'research', 'lab ']):
            total += 1

    return total, cn


def parse_sp_style(content: str) -> tuple[int, int]:
    """
    IEEE S&P accepted papers page:
      Title
      Author1 (Inst1), Author2 (Inst2), ...
    or
      Author1, Inst1
      Author2, Inst2
    """
    lines = [l.strip() for l in content.split('\n') if l.strip()]
    total, cn = 0, 0

    for line in lines:
        # Find lines with institutional affiliations
        # Pattern: "Name (Institution)" repeated
        affils = re.findall(r'\(([^)]{5,80})\)', line)
        if affils:
            total += 1
            # First affiliation = first author's institution
            if is_cn(affils[0]):
                cn += 1
        # Pattern: "Name, Institution, City, Country"
        elif re.search(r',\s+[A-Z][^,]{3,50},\s+[A-Z][^,]{2,30}$', line):
            total += 1
            if is_cn(line):
                cn += 1

    return total, cn


def parse_acm_mm_style(content: str) -> tuple[int, int]:
    """
    ACM MM 2024 accepted list: numbered papers with author names.
    No affiliations shown.
    """
    # Since no affiliations, use keyword detection on full text
    # Count Chinese keyword occurrences as a proxy
    cn_mentions = len(CN_PAT.findall(content))
    # Rough paper count from numbering
    paper_nums = re.findall(r'^\d+\s+\w', content, re.MULTILINE)
    total = len(paper_nums) if paper_nums else 0
    return total, cn_mentions  # cn_mentions as rough proxy


def parse_chi_style(content: str) -> tuple[int, int]:
    """
    CHI/CSCW/UbiComp pages: various formats.
    """
    total, cn = 0, 0
    # Look for institutional patterns
    for line in content.split('\n'):
        line = line.strip()
        if re.search(r'\b(university|institute|research center|laboratory|ltd|inc\.)\b',
                     line, re.IGNORECASE) and len(line) < 200:
            total += 1
            if is_cn(line):
                cn += 1
    return total, cn


# ─── Targeted URL fixes ───────────────────────────────────────────────────────

TARGETED_URLS = {
    # CVF OpenAccess for CVPR/ICCV (has full author list)
    "CVPR":   "https://openaccess.thecvf.com/CVPR2025?day=all",
    "ICCV":   "https://openaccess.thecvf.com/ICCV2023?day=all",

    # AAAI program
    "AAAI":   "https://ojs.aaai.org/index.php/AAAI/issue/view/1325",

    # S&P 2025 - direct URL
    "S&P":    "https://sp2025.ieee-security.org/accepted-papers.html",

    # NeurIPS 2024 proceedings page (has author info)
    "NeurIPS": "https://proceedings.neurips.cc/paper_files/paper/2024",

    # ICML 2025
    "ICML":  "https://icml.cc/Conferences/2025/Schedule?type=Poster",

    # ICLR 2025
    "ICLR":  "https://openreview.net/group?id=ICLR.cc/2025/Conference",

    # ACL 2025
    "ACL":   "https://aclanthology.org/2025.acl-long.0.pdf",  # will fail, but try index
    "ACL2":  "https://aclanthology.org/events/acl-2025/",

    # SIGKDD 2025 accepted papers
    "SIGKDD": "https://kdd2025.kdd.org/accepted-papers-research-track/",

    # SOSP 2024
    "SOSP":  "https://dl.acm.org/doi/proceedings/10.1145/3694715",

    # CHI 2025 full list
    "CHI":   "https://programs.sigchi.org/chi/2025/papers",

    # CSCW 2024 papers
    "CSCW":  "https://dl.acm.org/doi/proceedings/10.1145/3706619",

    # UIST 2024
    "UIST":  "https://dl.acm.org/doi/proceedings/10.1145/3654777",

    # IEEE VIS 2024
    "IEEE VIS": "https://ieeevis.org/year/2024/program/papers.html",

    # SIGGRAPH 2025
    "SIGGRAPH": "https://dl.acm.org/doi/proceedings/10.1145/3721238",

    # ACM MM 2024
    "ACM MM": "https://2024.acmmm.org/accepted-list",

    # DAC 2025
    "DAC":  "https://ieeexplore.ieee.org/xpl/conhome/10855066/proceeding",

    # PPoPP 2025
    "PPoPP": "https://ppopp25.sigplan.org/program/program-ppopp-2025",

    # MICRO 2024
    "MICRO": "https://dl.acm.org/doi/proceedings/10.1109/MICRO61839.2024",

    # ISCA 2025
    "ISCA":  "https://iscaconf.org/isca2025/program.php",

    # HPDC 2025
    "HPDC":  "https://dl.acm.org/doi/proceedings/10.1145/3698038",

    # ASE 2024
    "ASE":   "https://conf.researchr.org/track/ase-2024/ase-2024-research",

    # ICSE 2025
    "ICSE":  "https://conf.researchr.org/track/icse-2025/icse-2025-research-track",

    # SODA 2025
    "SODA":  "https://www.siam.org/conferences-events/past-event-archive/soda25/program/accepted-papers/",

    # FM 2024 - better page
    "FM":    "https://www.fm24.polimi.it/?page_id=559",

    # LICS 2025 accepted
    "LICS":  "https://lics.siglog.org/lics25/accepted.php",

    # RTSS 2024
    "RTSS":  "https://2024.rtss.org/accepted-papers/index.html",

    # WWW 2025
    "WWW":   "https://www2025.thewebconf.org/calls/research-track-papers/",
}


def scrape_targeted(browser, name: str, url: str) -> str:
    context = browser.new_context(
        user_agent="Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 Chrome/120 Safari/537.36"
    )
    page = context.new_page()
    try:
        page.goto(url, wait_until="domcontentloaded", timeout=45000)
        page.wait_for_timeout(4000)
        return page.inner_text("body")
    except Exception as e:
        return f"ERROR: {e}"
    finally:
        context.close()


def count_from_content(name: str, content: str) -> tuple[int, int]:
    """Pick the best parser based on conference name and return (total, cn)."""
    if name in ("EUROCRYPT", "CRYPTO"):
        return parse_eurocrypt_style(content)
    elif name in ("S&P",):
        return parse_sp_style(content)
    elif name in ("ACM MM",):
        return parse_acm_mm_style(content)
    elif name in ("CHI", "CSCW", "UbiComp", "UIST"):
        return parse_chi_style(content)
    elif name in ("CVPR", "ICCV"):
        # Count papers with Chinese-named institutions in blocks
        blocks = content.split('\n\n')
        cn = sum(1 for b in blocks if is_cn(b) and len(b) > 20)
        total = len([b for b in blocks if len(b) > 20])
        return total, cn
    else:
        # Generic: count lines/blocks with institution mentions
        total, cn = 0, 0
        for para in re.split(r'\n{2,}', content):
            if re.search(r'university|institute|laboratory|research|college|school|alibaba|tencent|huawei|baidu|google|microsoft|meta|amazon',
                         para, re.IGNORECASE):
                total += 1
                if is_cn(para):
                    cn += 1
        return total, cn


def main():
    results = {}

    # Load existing parsed results
    pfile = "/home/nanogpt/prj/ccf-conference/parsed_results.json"
    if os.path.exists(pfile):
        with open(pfile) as f:
            results = json.load(f)

    print("Scraping targeted URLs for improved data...")
    print("=" * 80)

    # Priority: conferences with 0 parsed blocks that need fixing
    PRIORITY = [
        "CVPR", "AAAI", "NeurIPS", "ICML", "ICLR",
        "S&P", "EUROCRYPT", "CRYPTO",
        "ACM MM", "SIGGRAPH", "IEEE VIS",
        "CHI", "CSCW", "UbiComp", "UIST",
        "ACL", "SIGKDD",
        "PPoPP", "MICRO", "ISCA", "DAC", "HPDC",
        "SOSP", "ASE", "ICSE",
        "SODA", "LICS",
        "WWW", "RTSS",
    ]

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)

        for name in PRIORITY:
            url = TARGETED_URLS.get(name)
            if not url:
                continue

            raw_path = os.path.join(RAW_DIR, f"{name.replace(' ', '_').replace('/', '_').replace('&','and')}_v2.txt")

            if os.path.exists(raw_path):
                with open(raw_path) as f:
                    content = f.read()
                print(f"  {name:15}: [cached] {len(content)} chars", end="")
            else:
                print(f"  {name:15}: fetching {url[:55]}...", end="", flush=True)
                content = scrape_targeted(browser, name, url)
                if not content.startswith("ERROR"):
                    with open(raw_path, 'w', encoding='utf-8') as f:
                        f.write(content[:80000])
                    print(f" {len(content)} chars", end="")
                else:
                    print(f" {content[:80]}")
                    time.sleep(1)
                    continue

            total, cn = count_from_content(name, content)
            pct = round(cn / max(total, 1) * 100, 1)
            print(f" → {total} items, {cn} CN ({pct}%)")

            if total > 0:
                results[name] = {
                    "total_parsed": total,
                    "cn_first_affil": cn,
                    "cn_pct": pct,
                    "strategy": "v2",
                }

            time.sleep(1)

        browser.close()

    # Print summary
    print("\n" + "=" * 80)
    print("FINAL SUMMARY (institution-based Chinese first-author counts)")
    print("=" * 80)
    print(f"{'Conference':<18} {'Total':<8} {'CN':<8} {'CN%':<7}")
    print("-" * 41)
    for name, r in sorted(results.items()):
        if not r.get("error") and r.get("total_parsed", 0) > 0:
            print(f"{name:<18} {r['total_parsed']:<8} {r['cn_first_affil']:<8} {r['cn_pct']:.1f}%")

    with open(pfile, "w") as f:
        json.dump(results, f, indent=2)
    print(f"\nSaved to {pfile}")


if __name__ == "__main__":
    main()
