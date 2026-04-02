#!/usr/bin/env python3
"""
Direct scraper: navigate to known conference program pages (not ACM DL),
extract text, count first-author Chinese-institution papers.

URLs sourced from: DBLP links + conference websites found in previous research.
"""

import re, json, time, os
from playwright.sync_api import sync_playwright
from urllib.parse import urljoin, urlparse

RAW_DIR = "/home/nanogpt/prj/ccf-conference/raw_direct"
os.makedirs(RAW_DIR, exist_ok=True)

# ── Chinese institution keyword pattern ───────────────────────────────────────
CN_PAT = re.compile(
    r'tsinghua|peking university|\bpku\b|beihang|\bbuaa\b|fudan|'
    r'zhejiang univ(?:ersity)?|\bzju\b|shanghai jiao tong|\bsjtu\b|'
    r'nanjing univ(?:ersity)?|\bnju\b|harbin inst(?:itute)?|\bhit\b|'
    r'univ(?:ersity)? of science and technology of china|\bustc\b|'
    r'beijing institute of technology|sun yat.sen|\bsysu\b|wuhan univ|tongji univ|'
    r'huazhong univ(?:ersity)?|\bhust\b|southeast univ|renmin univ|\bruc\b|'
    r'nankai|tianjin univ|shandong univ|jilin univ|'
    r'northeastern univ(?:ersity)?(?=.{0,30}china)|'
    r'northwestern polytechnical|\bnwpu\b|xidian|xi.an jiaotong|\bxjtu\b|'
    r'sichuan univ|chongqing univ|central south univ|'
    r'dalian(?:.*?tech(?:nology)?)|nat(?:ional)? univ(?:ersity)? of defense|\bnudt\b|'
    r'chinese academy of sciences|\bcas\b(?=.{0,20}china)|'
    r'inst(?:itute)? of computing technology|'
    r'inst(?:itute)? of information engineering|'
    r'shenzhen univ|sustech|westlake univ|shanghaitech|'
    r'chinese univ(?:ersity)? of hong kong|\bcuhk\b|'
    r'hong kong univ(?:ersity)? of sci(?:ence)?|\bhkust\b|'
    r'univ(?:ersity)? of hong kong|city univ(?:ersity)?.*?hong kong|'
    r'hong kong polytechnic|univ(?:ersity)? of macau|'
    r'alibaba|alipay|ant group|ant financial|'
    r'tencent|baidu|bytedance|huawei|didi|meituan|\bjd(?:\.com| ai)\b|'
    r'sensetime|megvii|xiaomi|iflytek|hikvision|kuaishou|\bkwai\b|'
    r'zhipu|deepseek|moonshot|minimax|stepfun|'
    r'china mobile|china unicom|china telecom|zhongguancun|'
    r', china\b|\(china\b|china\s*\)|china,\s*$|'
    r'hong kong|macau|macao|'
    r'\bbeijing\b|\bshanghai\b|\bshenzhen\b|\bguangzhou\b|'
    r'\bhangzhou\b|\bchengdu\b|\bnanjing\b|\bwuhan\b|'
    r'xi.an\b|\btianjin\b|\bhefei\b|\bchongqing\b|\bchangsha\b|\bqingdao\b',
    re.IGNORECASE
)

def is_cn(text: str) -> bool:
    return bool(CN_PAT.search(text or ""))

INST_KW = re.compile(
    r'university|universit[eéyä]|univ\b|institute|institution|laboratory|lab\b|'
    r'college|school of|department|faculty|'
    r'research center|research lab|r&d|'
    r'company|corporation|corp\b|inc\b|ltd\b|gmbh|s\.a\.|'
    r'google|microsoft|meta\b|amazon|apple|ibm|intel|nvidia|amd|qualcomm|'
    r'alibaba|tencent|baidu|bytedance|huawei|sensetime|megvii|'
    r'ntt |epfl|eth |inria|cnrs|rwth|mit\b|caltech|',
    re.IGNORECASE
)

# ── Conference URL catalogue ───────────────────────────────────────────────────
# For each conference: list of URLs to try (most specific first).
# We avoid ACM DL and IEEE Xplore proceedings pages.
CONFERENCES = {
    # ── Area 1: Computer Architecture ────────────────────────────────────────
    "PPoPP 2025":    ["https://ppopp25.sigplan.org/program/program-ppopp-2025"],
    "FAST 2025":     ["https://www.usenix.org/conference/fast25/technical-sessions"],
    "DAC 2025":      ["https://dac.com/2025/technical-program/",
                      "https://dac.com/2025/accepted-papers/"],
    "HPCA 2025":     ["https://hpca-conf.org/2025/main-program/"],
    "MICRO 2024":    ["https://microarch.org/micro57/index.php/program/"],
    "SC 2024":       ["https://sc24.supercomputing.org/program/papers/"],
    "ASPLOS 2025":   ["https://www.asplos-conference.org/asplos2025/program.html",
                      "https://www.asplos-conference.org/asplos2025/"],
    "ISCA 2025":     ["https://iscaconf.org/isca2025/program.php",
                      "https://iscaconf.org/isca2025/"],
    "USENIX ATC 2025": ["https://www.usenix.org/conference/atc25/technical-sessions"],
    "EuroSys 2025":  ["https://2025.eurosys.org/accepted-papers.html"],
    "HPDC 2025":     ["https://hpdc.sci.utah.edu/2025/program.html",
                      "https://hpdc.sci.utah.edu/2025/"],

    # ── Area 2: Networks ──────────────────────────────────────────────────────
    "SIGCOMM 2025":  ["https://conferences.sigcomm.org/sigcomm/2025/accepted-papers/"],
    "MobiCom 2024":  ["https://www.sigmobile.org/mobicom/2024/accepted.html"],
    "INFOCOM 2025":  ["https://infocom2025.ieee-infocom.org/program/accepted-paper-list-main-conference"],
    "NSDI 2025":     ["https://www.usenix.org/conference/nsdi25/technical-sessions"],

    # ── Area 3: Security ─────────────────────────────────────────────────────
    "CCS 2024":      ["https://www.sigsac.org/ccs/CCS2024/program/accepted-papers.html"],
    "EUROCRYPT 2025": ["https://eurocrypt.iacr.org/2025/acceptedpapers.php"],
    "S&P 2025":      ["https://sp2025.ieee-security.org/accepted-papers.html"],
    "CRYPTO 2024":   ["https://crypto.iacr.org/2024/acceptedpapers.php"],
    "USENIX Security 2025": ["https://www.usenix.org/conference/usenixsecurity25/technical-sessions"],
    "NDSS 2025":     ["https://www.ndss-symposium.org/ndss2025/accepted-papers/"],

    # ── Area 4: Software Engineering ─────────────────────────────────────────
    "PLDI 2025":     ["https://pldi25.sigplan.org/track/pldi-2025-papers"],
    "POPL 2025":     ["https://popl25.sigplan.org/track/POPL-2025-popl-research-papers"],
    "FSE 2025":      ["https://conf.researchr.org/track/fse-2025/fse-2025-research-papers"],
    "SOSP 2024":     ["https://sigops.org/s/conferences/sosp/2024/program.html",
                      "https://sosp2024.mpi-sws.org/program.html"],
    "OOPSLA 2024":   ["https://2024.splashcon.org/track/splash-2024-oopsla",
                      "https://conf.researchr.org/track/splash-2024/splash-2024-oopsla"],
    "ASE 2024":      ["https://conf.researchr.org/track/ase-2024/ase-2024-research"],
    "ICSE 2025":     ["https://conf.researchr.org/track/icse-2025/icse-2025-research-track"],
    "ISSTA 2025":    ["https://conf.researchr.org/track/issta-2025/issta-2025-papers"],
    "OSDI 2024":     ["https://www.usenix.org/conference/osdi24/technical-sessions"],
    "FM 2024":       ["https://www.fm24.polimi.it/?page_id=559",
                      "https://fm2024.github.io/program.html"],

    # ── Area 5: Database ─────────────────────────────────────────────────────
    "SIGMOD 2025":   ["https://2025.sigmod.org/sigmod_papers.shtml"],
    "SIGKDD 2025":   ["https://kdd2025.kdd.org/accepted-papers-research-track/",
                      "https://kdd2025.kdd.org/program/"],
    "ICDE 2025":     ["https://ieee-icde.org/2025/research-papers/"],
    "SIGIR 2025":    ["https://sigir2025.dei.unipd.it/accepted-papers.html"],
    "VLDB 2025":     ["https://vldb.org/2025/?papers-research"],

    # ── Area 6: Theory ───────────────────────────────────────────────────────
    "STOC 2025":     ["https://acm-stoc.org/stoc2025/accepted-papers.html"],
    "SODA 2025":     ["https://www.siam.org/conferences-events/past-event-archive/soda25/program/accepted-papers/"],
    "CAV 2025":      ["https://conferences.i-cav.org/2025/accepted/"],
    "FOCS 2024":     ["https://focs.computer.org/2024/accepted-papers-for-focs-2024/"],
    "LICS 2025":     ["https://lics.siglog.org/lics25/accepted.php"],

    # ── Area 7: Graphics & Multimedia ────────────────────────────────────────
    "ACM MM 2024":   ["https://2024.acmmm.org/accepted-list",
                      "https://2024.acmmm.org/"],
    "SIGGRAPH 2025": ["https://s2025.siggraph.org/program/technical-papers/",
                      "https://kesen.realtimerendering.com/sig2025.html"],
    "VR 2025":       ["https://ieeevr.org/2025/program/papers/"],
    "IEEE VIS 2024": ["https://ieeevis.org/year/2024/program/papers.html"],

    # ── Area 8: AI ───────────────────────────────────────────────────────────
    "AAAI 2025":     ["https://ojs.aaai.org/index.php/AAAI/issue/view/1325",
                      "https://aaai.org/aaai-publications/aaai-conference-proceedings/aaai-25-technical-program/"],
    "NeurIPS 2024":  ["https://proceedings.neurips.cc/paper_files/paper/2024"],
    "ACL 2025":      ["https://aclanthology.org/events/acl-2025/"],
    "CVPR 2025":     ["https://cvpr.thecvf.com/Conferences/2025/AcceptedPapers"],
    "ICCV 2023":     ["https://openaccess.thecvf.com/ICCV2023.py",
                      "https://iccv2023.thecvf.com/main_conference_papers/"],
    "ICML 2025":     ["https://icml.cc/Conferences/2025/Schedule?type=Poster"],
    "ICLR 2025":     ["https://iclr.cc/Conferences/2025/Schedule?type=Poster"],

    # ── Area 9: HCI ──────────────────────────────────────────────────────────
    "CSCW 2024":     ["https://cscw.acm.org/2024/index.php/accepted-papers/"],
    "CHI 2025":      ["https://programs.sigchi.org/chi/2025/papers",
                      "https://chi2025.acm.org/"],
    "UbiComp 2024":  ["https://www.ubicomp.org/ubicomp-iswc-2024/program/"],
    "UIST 2024":     ["https://uist.acm.org/2024/program/"],

    # ── Area 10: Interdisciplinary ────────────────────────────────────────────
    "WWW 2025":      ["https://www2025.thewebconf.org/",
                      "https://thewebconf.org/www2025/"],
    "RTSS 2024":     ["https://2024.rtss.org/accepted-papers/index.html"],
}


# ── Parsers ───────────────────────────────────────────────────────────────────

def parse_usenix(content: str) -> tuple[int, int]:
    """
    USENIX format (ATC, OSDI, NSDI, FAST, Security):
      Paper Title
      Author1, Author2, Institution1; Author3, Institution2
      AVAILABLE MEDIA
    First author's affil = institution in first semicolon-group.
    """
    total, cn = 0, 0
    lines = [l.strip() for l in content.split('\n')]
    i = 0
    while i < len(lines) - 1:
        curr = lines[i]
        nxt  = lines[i + 1] if i + 1 < len(lines) else ""
        # heuristic: a short title line followed by an author+affil line
        if (10 < len(curr) < 200
                and not curr.startswith(('Session', 'Track', 'Chair', 'Monday',
                                          'Tuesday', 'Wednesday', 'Thursday',
                                          'Friday', 'Coffee', 'AVAILABLE', 'Proceedings',
                                          'USENIX', 'Full', 'Attendee'))):
            # Author line contains semicolons or commas with institution keywords
            if (';' in nxt or INST_KW.search(nxt)) and len(nxt) > 10:
                first_group = nxt.split(';')[0]
                parts = first_group.split(',')
                affil = parts[-1].strip() if len(parts) >= 2 else first_group
                if len(affil) > 3:
                    total += 1
                    if is_cn(affil) or is_cn(first_group):
                        cn += 1
        i += 1
    return total, cn


def parse_infocom_style(content: str) -> tuple[int, int]:
    """
    "(Institution, Country)" after author names.
    Count first parenthesized affiliation per paper block.
    """
    total, cn = 0, 0
    blocks = re.split(r'\n{2,}', content)
    for block in blocks:
        block = block.strip()
        if len(block) < 20:
            continue
        affils = re.findall(r'\(([^)]{5,120})\)', block)
        first_affil = next((a for a in affils if INST_KW.search(a)), None)
        if first_affil:
            total += 1
            if is_cn(first_affil):
                cn += 1
    return total, cn


def parse_ccs_style(content: str) -> tuple[int, int]:
    """
    CCS / NDSS: lines like "Author (Institution)"
    Count first author per paper.
    """
    total, cn = 0, 0
    # tab-separated: "Title<TAB>Author (Institution)"
    for line in content.split('\n'):
        if '\t' in line:
            parts = line.split('\t')
            author_part = parts[1] if len(parts) > 1 else ""
            m = re.search(r'\(([^)]+)\)', author_part)
            if m and INST_KW.search(m.group(1)):
                total += 1
                if is_cn(m.group(1)):
                    cn += 1
    # Also: "Name (Institution)\n" lines
    if total < 5:
        seen_titles = set()
        for line in content.split('\n'):
            line = line.strip()
            m = re.match(r'^([^(]+)\s*\(([^)]{5,80})\)\s*$', line)
            if m and INST_KW.search(m.group(2)) and m.group(2) not in seen_titles:
                seen_titles.add(m.group(2))
                total += 1
                if is_cn(m.group(2)):
                    cn += 1
    return total, cn


def parse_iacr_style(content: str) -> tuple[int, int]:
    """
    IACR (EUROCRYPT/CRYPTO):
      Title
      Author1, Author2
      Institution
    """
    total, cn = 0, 0
    lines = [l.strip() for l in content.split('\n') if l.strip()]
    i = 0
    while i < len(lines) - 2:
        maybe_inst = lines[i + 1]
        if INST_KW.search(maybe_inst) and not INST_KW.search(lines[i]):
            total += 1
            if is_cn(maybe_inst):
                cn += 1
            i += 2
        else:
            i += 1
    return total, cn


def parse_sigplan_style(content: str) -> tuple[int, int]:
    """
    SIGPLAN / conf.researchr pages (PLDI, POPL, ICSE, FSE, ASE…):
    Flexible: look for "Name, Institution" or "(Institution)" patterns.
    """
    total, cn = 0, 0
    for line in content.split('\n'):
        line = line.strip()
        # "Name, Institution, City" pattern
        m = re.match(
            r'^[A-Z][^,]{1,40},\s+(.{5,80}(?:university|institute|lab|school|'
            r'research|college|corporation|inc\.|ltd|gmbh|google|microsoft|meta|'
            r'amazon|apple|ibm|intel|nvidia|alibaba|tencent|baidu|huawei)[^,\n]{0,60})$',
            line, re.IGNORECASE
        )
        if m:
            total += 1
            if is_cn(m.group(1)):
                cn += 1
            continue
        # "(Institution)"
        m2 = re.search(r'\(([^)]{5,80}(?:university|institute|lab|school|'
                        r'research|corp|inc\.)[^)]{0,40})\)', line, re.IGNORECASE)
        if m2:
            total += 1
            if is_cn(m2.group(1)):
                cn += 1
    return total, cn


def parse_theory_style(content: str) -> tuple[int, int]:
    """
    Theory conferences (STOC, FOCS, SODA, CAV, LICS):
    Look for "(Institution)" per line, first occurrence = first author.
    """
    total, cn = 0, 0
    for line in content.split('\n'):
        line = line.strip()
        affils = re.findall(r'\(([^)]{5,100})\)', line)
        for affil in affils:
            if INST_KW.search(affil):
                total += 1
                if is_cn(affil):
                    cn += 1
                break
    return total, cn


def parse_generic(content: str) -> tuple[int, int]:
    """
    Fallback: scan paragraph blocks, find first institution, check if CN.
    """
    total, cn = 0, 0
    blocks = re.split(r'\n{2,}|<br\s*/?>|(?<=\n)[-─]{5,}', content)
    for block in blocks:
        block = block.strip()
        if len(block) < 15:
            continue
        for line in block.split('\n'):
            line = line.strip()
            if INST_KW.search(line) and 5 < len(line) < 200:
                total += 1
                if is_cn(line):
                    cn += 1
                break
    # Fallback to parenthesized affiliations
    if total < 5:
        for line in content.split('\n'):
            affils = re.findall(r'\(([^)]{5,100})\)', line)
            for affil in affils:
                if INST_KW.search(affil):
                    total += 1
                    if is_cn(affil):
                        cn += 1
                    break
    return total, cn


PARSER_MAP = {
    "FAST 2025": parse_usenix,
    "USENIX ATC 2025": parse_usenix,
    "NSDI 2025": parse_usenix,
    "USENIX Security 2025": parse_usenix,
    "OSDI 2024": parse_usenix,
    "INFOCOM 2025": parse_infocom_style,
    "VR 2025": parse_infocom_style,
    "CCS 2024": parse_ccs_style,
    "NDSS 2025": parse_ccs_style,
    "EUROCRYPT 2025": parse_iacr_style,
    "CRYPTO 2024": parse_iacr_style,
    "PLDI 2025": parse_sigplan_style,
    "POPL 2025": parse_sigplan_style,
    "FSE 2025": parse_sigplan_style,
    "OOPSLA 2024": parse_sigplan_style,
    "ASE 2024": parse_sigplan_style,
    "ICSE 2025": parse_sigplan_style,
    "ISSTA 2025": parse_sigplan_style,
    "STOC 2025": parse_theory_style,
    "SODA 2025": parse_theory_style,
    "FOCS 2024": parse_theory_style,
    "CAV 2025": parse_theory_style,
    "LICS 2025": parse_theory_style,
}


# ── Sub-page navigation ────────────────────────────────────────────────────────
PROGRAM_RE = re.compile(
    r'accepted.papers?|technical.sessions?|research.papers?|'
    r'full.program|program.papers?|paper.list',
    re.IGNORECASE
)

def find_program_link(page, base_url: str) -> str | None:
    base_domain = urlparse(base_url).netloc
    for a in page.query_selector_all("a[href]"):
        try:
            text = (a.inner_text() or "").strip()
            href = a.get_attribute("href") or ""
            if PROGRAM_RE.search(text) or PROGRAM_RE.search(href):
                if href.startswith("/"):
                    href = urljoin(base_url, href)
                if urlparse(href).netloc == base_domain:
                    return href
        except Exception:
            continue
    return None


# ── Main processing ────────────────────────────────────────────────────────────
def fetch_page(page, url: str, timeout_ms: int = 30000) -> str:
    try:
        page.goto(url, wait_until="domcontentloaded", timeout=timeout_ms)
        page.wait_for_timeout(3000)
        content = page.inner_text("body")
        return content
    except Exception as e:
        return f"ERROR: {e}"


def process_conference(browser, display_name: str, url_list: list) -> dict:
    ctx = browser.new_context(
        user_agent="Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
                   "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
        viewport={"width": 1280, "height": 900},
    )
    page = ctx.new_page()

    try:
        content = ""
        used_url = ""

        for url in url_list:
            print(f"    → {url[:70]}", end="", flush=True)
            text = fetch_page(page, url)
            if text.startswith("ERROR"):
                print(f"  {text[:60]}")
                continue

            print(f"  ({len(text)} chars)", end="")

            # Check if this page has useful affiliation content
            if INST_KW.search(text) and len(text) > 3000:
                content = text
                used_url = url
                print(" ✓")
                break

            # Try to find a program/accepted-papers sub-link on this page
            sub = find_program_link(page, url)
            if sub and sub != url:
                print(f"\n    sub→ {sub[:70]}", end="", flush=True)
                sub_text = fetch_page(page, sub)
                if not sub_text.startswith("ERROR") and INST_KW.search(sub_text) and len(sub_text) > 3000:
                    content = sub_text
                    used_url = sub
                    print(f"  ({len(sub_text)} chars) ✓")
                    break
                else:
                    print(" (no affil content)")
            else:
                print(" (no sub-link)")

        if not content:
            return {"name": display_name, "url": used_url, "total": 0, "cn": 0,
                    "pct": 0.0, "error": "no useful content found"}

        # Save raw
        safe = display_name.replace(' ', '_').replace('/', '_').replace('&', 'and')
        with open(os.path.join(RAW_DIR, f"{safe}.txt"), "w", encoding="utf-8") as f:
            f.write(f"URL: {used_url}\n\n{content[:80000]}")

        # Parse
        parser = PARSER_MAP.get(display_name, parse_generic)
        total, cn = parser(content)

        # If the specific parser finds < 5 blocks, also try generic
        if total < 5:
            g_total, g_cn = parse_generic(content)
            if g_total > total:
                total, cn = g_total, g_cn

        pct = round(cn / max(total, 1) * 100, 1)
        print(f"    RESULT: {total} blocks, {cn} CN ({pct}%)")

        return {"name": display_name, "url": used_url,
                "total": total, "cn": cn, "pct": pct, "error": None}

    finally:
        ctx.close()


def main():
    results = []
    conf_list = list(CONFERENCES.items())
    n = len(conf_list)

    print(f"Directly scraping {n} conference program pages")
    print("=" * 80)

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)

        for i, (name, urls) in enumerate(conf_list):
            # Check cache
            safe = name.replace(' ', '_').replace('/', '_').replace('&', 'and')
            cache_path = os.path.join(RAW_DIR, f"{safe}.txt")
            if os.path.exists(cache_path) and os.path.getsize(cache_path) > 3000:
                print(f"[{i+1}/{n}] {name}  [cached]")
                with open(cache_path) as f:
                    content = f.read()
                used_url = content.split('\n')[0].replace("URL: ", "")
                parser = PARSER_MAP.get(name, parse_generic)
                total, cn = parser(content)
                if total < 5:
                    g_total, g_cn = parse_generic(content)
                    if g_total > total:
                        total, cn = g_total, g_cn
                pct = round(cn / max(total, 1) * 100, 1)
                print(f"    RESULT: {total} blocks, {cn} CN ({pct}%)")
                results.append({"name": name, "url": used_url,
                                 "total": total, "cn": cn, "pct": pct, "error": None})
            else:
                print(f"\n[{i+1}/{n}] {name}")
                result = process_conference(browser, name, urls)
                results.append(result)
            time.sleep(1)

        browser.close()

    # ── Summary ──────────────────────────────────────────────────────────────
    print("\n" + "=" * 80)
    print("RESULTS SUMMARY")
    print("=" * 80)
    print(f"{'Conference':<25} {'Total':>7} {'CN':>6} {'CN%':>7}  URL")
    print("-" * 90)
    for r in results:
        url_s = (r.get("url") or "")[:45]
        if r.get("error") and r.get("total", 0) == 0:
            print(f"{r['name']:<25} {'ERR':>7}  {r.get('error','')[:40]}")
        else:
            print(f"{r['name']:<25} {r.get('total',0):>7} {r.get('cn',0):>6} "
                  f"{r.get('pct',0):>6.1f}%  {url_s}")

    # Save
    out = "/home/nanogpt/prj/ccf-conference/direct_results.json"
    with open(out, "w", encoding="utf-8") as f:
        json.dump(results, f, ensure_ascii=False, indent=2)
    print(f"\n→ Saved to {out}")


if __name__ == "__main__":
    main()
