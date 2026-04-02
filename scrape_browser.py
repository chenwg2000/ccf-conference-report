#!/usr/bin/env python3
"""
Scrape conference program/accepted-papers pages using Playwright headless browser.
Extracts first-author affiliations to count Chinese-institution papers.

Chinese institutions detected by keywords in affiliation text.
"""

import re
import json
import time
import os
from playwright.sync_api import sync_playwright

# Keywords that identify Chinese institutions
CN_KEYWORDS = [
    # Universities
    "tsinghua", "peking university", "pku", "beihang", "buaa",
    "fudan", "zhejiang university", "zju", "shanghai jiao tong", "sjtu",
    "nanjing university", "nju", "harbin institute", "hit",
    "university of science and technology of china", "ustc",
    "beijing institute of technology", "bit",
    "sun yat-sen", "sysu", "wuhan university", "tongji",
    "huazhong university", "hust", "southeast university",
    "renmin university", "ruc", "nankai", "tianjin university",
    "shandong university", "jilin university", "northeastern university",
    "northwestern polytechnical", "nwpu", "xidian", "xi'an jiaotong",
    "xjtu", "sichuan university", "chongqing university",
    "central south university", "csu", "dalian university",
    "national university of defense technology", "nudt",
    "chinese academy of sciences", "cas ", "ict, chinese",
    "institute of computing technology", "institute of information engineering",
    "institute of software", "academy of mathematics",
    "shenzhen university", "southern university of science",
    "sustech", "westlake university", "shanghaitech",
    "chinese university of hong kong", "cuhk",
    "hong kong university of science", "hkust",
    "university of hong kong", "city university of hong kong",
    "hong kong polytechnic", "hong kong baptist",
    "university of macau", "national taiwan", "ntu", "nthu", "nctu",
    # Companies (Chinese tech)
    "alibaba", "tencent", "baidu", "huawei", "bytedance",
    "didi", "meituan", "jd.com", "jd ai", "netease",
    "sensetime", "megvii", "face++", "zhipu", "moonshot",
    "deepseek", "minimax", "stepfun", "01.ai", "zhiyuan",
    "ant group", "ant financial", "alipay",
    "xiaomi", "oppo", "vivo", "oneplus", "meizu",
    "iflytek", "hikvision", "dahua",
    "china mobile", "china unicom", "china telecom",
    "lenovo research", "jd research", "kwai", "kuaishou",
    "pinduoduo", "mango", "bilibili",
    # General
    "china", "beijing", "shanghai", "shenzhen", "guangzhou",
    "hangzhou", "chengdu", "nanjing", "wuhan", "xi'an",
    "tianjin", "hefei", "chongqing", "fuzhou", "qingdao",
]

# Build regex for fast matching
CN_PATTERN = re.compile(
    r'\b(' + '|'.join(re.escape(k) for k in CN_KEYWORDS) + r')\b',
    re.IGNORECASE
)


def is_chinese_institution(affiliation: str) -> bool:
    """Check if affiliation text indicates a Chinese institution."""
    if not affiliation:
        return False
    return bool(CN_PATTERN.search(affiliation))


def clean_text(text: str) -> str:
    return ' '.join(text.split())


# Conference definitions: name, url, scraping strategy
# strategy: 'usenix' | 'acm_dl' | 'cvf' | 'generic' | 'neurips' | 'icml_pmlr' | 'openreview'
CONFERENCES = {
    # ---- Area 1: Computer Architecture ----
    "PPoPP": {
        "url": "https://dl.acm.org/doi/proceedings/10.1145/3710848",
        "strategy": "acm_dl", "year": 2025,
    },
    "FAST": {
        "url": "https://www.usenix.org/conference/fast25/technical-sessions",
        "strategy": "usenix", "year": 2025,
    },
    "DAC": {
        "url": "https://dl.acm.org/doi/proceedings/10.5555/3778334",
        "strategy": "acm_dl", "year": 2025,
    },
    "HPCA": {
        "url": "https://hpca-conf.org/2025/main-program/",
        "strategy": "generic_list", "year": 2025,
    },
    "MICRO": {
        "url": "https://dl.acm.org/doi/proceedings/10.1145/3669940",
        "strategy": "acm_dl", "year": 2024,
    },
    "SC": {
        "url": "https://sc24.supercomputing.org/program/papers/",
        "strategy": "generic_list", "year": 2024,
    },
    "ASPLOS": {
        "url": "https://dl.acm.org/doi/proceedings/10.1145/3669940",
        "strategy": "acm_dl", "year": 2025,
    },
    "ISCA": {
        "url": "https://dl.acm.org/doi/proceedings/10.1145/3695053",
        "strategy": "acm_dl", "year": 2025,
    },
    "USENIX ATC": {
        "url": "https://www.usenix.org/conference/atc25/technical-sessions",
        "strategy": "usenix", "year": 2025,
    },
    "EuroSys": {
        "url": "https://dl.acm.org/doi/proceedings/10.1145/3689031",
        "strategy": "acm_dl", "year": 2025,
    },
    "HPDC": {
        "url": "https://dl.acm.org/doi/proceedings/10.1145/3698038",
        "strategy": "acm_dl", "year": 2025,
    },

    # ---- Area 2: Networks ----
    "SIGCOMM": {
        "url": "https://dl.acm.org/doi/proceedings/10.1145/3718958",
        "strategy": "acm_dl", "year": 2025,
    },
    "MobiCom": {
        "url": "https://dl.acm.org/doi/proceedings/10.1145/3636534",
        "strategy": "acm_dl", "year": 2024,
    },
    "INFOCOM": {
        "url": "https://infocom2025.ieee-infocom.org/program/accepted-paper-list-main-conference",
        "strategy": "generic_list", "year": 2025,
    },
    "NSDI": {
        "url": "https://www.usenix.org/conference/nsdi25/technical-sessions",
        "strategy": "usenix", "year": 2025,
    },

    # ---- Area 3: Security ----
    "CCS": {
        "url": "https://www.sigsac.org/ccs/CCS2024/program/accepted-papers.html",
        "strategy": "generic_list", "year": 2024,
    },
    "EUROCRYPT": {
        "url": "https://eurocrypt.iacr.org/2025/acceptedpapers.php",
        "strategy": "generic_list", "year": 2025,
    },
    "S&P": {
        "url": "https://sp2025.ieee-security.org/accepted-papers.html",
        "strategy": "generic_list", "year": 2025,
    },
    "CRYPTO": {
        "url": "https://crypto.iacr.org/2024/acceptedpapers.php",
        "strategy": "generic_list", "year": 2024,
    },
    "USENIX Security": {
        "url": "https://www.usenix.org/conference/usenixsecurity25/technical-sessions",
        "strategy": "usenix", "year": 2025,
    },
    "NDSS": {
        "url": "https://www.ndss-symposium.org/ndss2025/accepted-papers/",
        "strategy": "generic_list", "year": 2025,
    },

    # ---- Area 4: Software Engineering ----
    "PLDI": {
        "url": "https://pldi25.sigplan.org/track/pldi-2025-papers",
        "strategy": "sigplan", "year": 2025,
    },
    "POPL": {
        "url": "https://popl25.sigplan.org/track/POPL-2025-popl-research-papers",
        "strategy": "sigplan", "year": 2025,
    },
    "FSE": {
        "url": "https://conf.researchr.org/track/fse-2025/fse-2025-research-papers",
        "strategy": "researchr", "year": 2025,
    },
    "SOSP": {
        "url": "https://dl.acm.org/doi/proceedings/10.1145/3694715",
        "strategy": "acm_dl", "year": 2024,
    },
    "OOPSLA": {
        "url": "https://2024.splashcon.org/track/splash-2024-oopsla",
        "strategy": "researchr", "year": 2024,
    },
    "ASE": {
        "url": "https://dl.acm.org/doi/proceedings/10.1145/3691620",
        "strategy": "acm_dl", "year": 2024,
    },
    "ICSE": {
        "url": "https://conf.researchr.org/track/icse-2025/icse-2025-research-track",
        "strategy": "researchr", "year": 2025,
    },
    "ISSTA": {
        "url": "https://conf.researchr.org/track/issta-2025/issta-2025-papers",
        "strategy": "researchr", "year": 2025,
    },
    "OSDI": {
        "url": "https://www.usenix.org/conference/osdi24/technical-sessions",
        "strategy": "usenix", "year": 2024,
    },
    "FM": {
        "url": "https://www.fm24.polimi.it/?page_id=559",
        "strategy": "generic_list", "year": 2024,
    },

    # ---- Area 5: Database ----
    "SIGMOD": {
        "url": "https://2025.sigmod.org/sigmod_papers.shtml",
        "strategy": "generic_list", "year": 2025,
    },
    "SIGKDD": {
        "url": "https://dl.acm.org/doi/proceedings/10.1145/3690624",
        "strategy": "acm_dl", "year": 2025,
    },
    "ICDE": {
        "url": "https://ieee-icde.org/2025/research-papers/",
        "strategy": "generic_list", "year": 2025,
    },
    "SIGIR": {
        "url": "https://sigir2025.dei.unipd.it/accepted-papers.html",
        "strategy": "generic_list", "year": 2025,
    },
    "VLDB": {
        "url": "https://vldb.org/2025/?program-schedule",
        "strategy": "generic_list", "year": 2025,
    },

    # ---- Area 6: Theory ----
    "STOC": {
        "url": "https://acm-stoc.org/stoc2025/accepted-papers.html",
        "strategy": "generic_list", "year": 2025,
    },
    "SODA": {
        "url": "https://www.siam.org/conferences-events/past-event-archive/soda25/program/accepted-papers/",
        "strategy": "generic_list", "year": 2025,
    },
    "CAV": {
        "url": "https://conferences.i-cav.org/2025/accepted/",
        "strategy": "generic_list", "year": 2025,
    },
    "FOCS": {
        "url": "https://focs.computer.org/2024/accepted-papers-for-focs-2024/",
        "strategy": "generic_list", "year": 2024,
    },
    "LICS": {
        "url": "https://lics.siglog.org/lics25/accepted.php",
        "strategy": "generic_list", "year": 2025,
    },

    # ---- Area 7: Graphics/Multimedia ----
    "ACM MM": {
        "url": "https://dl.acm.org/doi/proceedings/10.1145/3664647",
        "strategy": "acm_dl", "year": 2024,
    },
    "SIGGRAPH": {
        "url": "https://dl.acm.org/doi/proceedings/10.1145/3721238",
        "strategy": "acm_dl", "year": 2025,
    },
    "VR": {
        "url": "https://ieeevr.org/2025/program/papers/",
        "strategy": "generic_list", "year": 2025,
    },
    "IEEE VIS": {
        "url": "https://ieeevis.org/year/2024/program/papers.html",
        "strategy": "generic_list", "year": 2024,
    },

    # ---- Area 8: AI ----
    "AAAI": {
        "url": "https://aaai.org/aaai-publications/aaai-conference-proceedings/aaai-25-technical-program/",
        "strategy": "generic_list", "year": 2025,
    },
    "NeurIPS": {
        "url": "https://neurips.cc/virtual/2024/papers.html",
        "strategy": "neurips", "year": 2024,
    },
    "ACL": {
        "url": "https://aclanthology.org/events/acl-2025/",
        "strategy": "acl_anthology", "year": 2025,
    },
    "CVPR": {
        "url": "https://cvpr.thecvf.com/Conferences/2025/AcceptedPapers",
        "strategy": "cvf", "year": 2025,
    },
    "ICCV": {
        "url": "https://openaccess.thecvf.com/ICCV2023?day=all",
        "strategy": "cvf", "year": 2023,
    },
    "ICML": {
        "url": "https://icml.cc/virtual/2025/papers.html",
        "strategy": "neurips", "year": 2025,
    },
    "ICLR": {
        "url": "https://iclr.cc/virtual/2025/papers.html",
        "strategy": "neurips", "year": 2025,
    },

    # ---- Area 9: HCI ----
    "CSCW": {
        "url": "https://dl.acm.org/doi/proceedings/10.1145/3686010",
        "strategy": "acm_dl", "year": 2024,
    },
    "CHI": {
        "url": "https://dl.acm.org/doi/proceedings/10.1145/3706598",
        "strategy": "acm_dl", "year": 2025,
    },
    "UbiComp": {
        "url": "https://dl.acm.org/doi/proceedings/10.1145/3675094",
        "strategy": "acm_dl", "year": 2024,
    },
    "UIST": {
        "url": "https://dl.acm.org/doi/proceedings/10.1145/3654777",
        "strategy": "acm_dl", "year": 2024,
    },

    # ---- Area 10: Interdisciplinary ----
    "WWW": {
        "url": "https://dl.acm.org/doi/proceedings/10.1145/3696410",
        "strategy": "acm_dl", "year": 2025,
    },
    "RTSS": {
        "url": "https://2024.rtss.org/accepted-papers/index.html",
        "strategy": "generic_list", "year": 2024,
    },
}


def scrape_usenix(page, url: str) -> list[dict]:
    """Scrape USENIX technical sessions page for papers with author affiliations."""
    page.goto(url, wait_until="networkidle", timeout=30000)
    papers = []

    # USENIX pages list papers in .paper-title / .authors blocks
    items = page.query_selector_all(".paper-title")
    if not items:
        # Try alternate selectors
        items = page.query_selector_all("h3.title, .views-row")

    for item in items:
        title = clean_text(item.inner_text())
        # Get sibling/parent for authors+affiliation
        parent = item.evaluate_handle("el => el.closest('.views-row, article, .paper')")
        try:
            authors_text = clean_text(parent.as_element().inner_text() if parent else "")
        except Exception:
            authors_text = ""
        papers.append({"title": title, "context": authors_text})

    # Alternative: grab all text blocks that have author+affiliation patterns
    if not papers:
        content = page.inner_text("body")
        papers = [{"title": "full_page", "context": content}]

    return papers


def scrape_generic_list(page, url: str) -> list[dict]:
    """Generic scraper: get all visible text from the page."""
    page.goto(url, wait_until="networkidle", timeout=30000)
    # Wait a bit for dynamic content
    page.wait_for_timeout(2000)
    content = page.inner_text("body")
    return [{"title": "full_page", "context": content}]


def scrape_acm_dl(page, url: str) -> list[dict]:
    """
    Scrape ACM DL proceedings page.
    Each paper listing includes title + authors with affiliations.
    """
    page.goto(url, wait_until="networkidle", timeout=30000)
    page.wait_for_timeout(3000)

    papers = []
    # ACM DL paper items
    items = page.query_selector_all("li.search__item, .issue-item")
    for item in items:
        try:
            title_el = item.query_selector(".hlFld-Title, h5.issue-item__title")
            title = clean_text(title_el.inner_text()) if title_el else ""
            # Authors with affiliations are in .author-info or tooltip
            context = clean_text(item.inner_text())
            papers.append({"title": title, "context": context})
        except Exception:
            pass

    if not papers:
        # Fallback: get full page text
        content = page.inner_text("main, body")
        papers = [{"title": "full_page", "context": content}]
    return papers


def scrape_cvf(page, url: str) -> list[dict]:
    """Scrape CVF open access (CVPR/ICCV) pages."""
    page.goto(url, wait_until="networkidle", timeout=30000)
    page.wait_for_timeout(2000)
    content = page.inner_text("body")
    return [{"title": "full_page", "context": content}]


def scrape_researchr(page, url: str) -> list[dict]:
    """Scrape conf.researchr.org pages (ICSE, FSE, ISSTA, OOPSLA)."""
    page.goto(url, wait_until="networkidle", timeout=30000)
    page.wait_for_timeout(3000)
    content = page.inner_text("body")
    return [{"title": "full_page", "context": content}]


def scrape_sigplan(page, url: str) -> list[dict]:
    """Scrape sigplan.org conference pages."""
    page.goto(url, wait_until="networkidle", timeout=30000)
    page.wait_for_timeout(3000)
    content = page.inner_text("body")
    return [{"title": "full_page", "context": content}]


def scrape_neurips(page, url: str) -> list[dict]:
    """Scrape NeurIPS/ICML/ICLR virtual site."""
    page.goto(url, wait_until="networkidle", timeout=60000)
    page.wait_for_timeout(5000)
    content = page.inner_text("body")
    return [{"title": "full_page", "context": content}]


def scrape_acl_anthology(page, url: str) -> list[dict]:
    """Scrape ACL Anthology."""
    page.goto(url, wait_until="networkidle", timeout=30000)
    page.wait_for_timeout(2000)
    content = page.inner_text("body")
    return [{"title": "full_page", "context": content}]


SCRAPERS = {
    "usenix": scrape_usenix,
    "acm_dl": scrape_acm_dl,
    "cvf": scrape_cvf,
    "researchr": scrape_researchr,
    "sigplan": scrape_sigplan,
    "neurips": scrape_neurips,
    "acl_anthology": scrape_acl_anthology,
    "generic_list": scrape_generic_list,
}


def count_chinese_from_text(content: str) -> tuple[int, int]:
    """
    Parse scraped page text to count total papers and Chinese-institution first-author papers.
    Returns (total_papers, chinese_papers).

    Heuristic: look for "Author1 (Affiliation1), Author2 (Affiliation2)" patterns
    or affiliation lines that follow author lines.
    """
    # Strategy: find blocks that look like "title\nauthors + affiliations"
    # Count sections with Chinese affiliations in the first author position

    cn_count = 0
    total_count = 0

    # Pattern 1: "(Affiliation)" after first author name
    # Matches: "Name Name (Institution, City)"
    aff_pattern = re.compile(
        r'^(.+?)\s*[\(\[]([^\)\]]+)[\)\]]',
        re.MULTILINE
    )

    # Pattern 2: Lines that are clearly affiliation lines
    # after paper title lines
    lines = content.split('\n')

    # Try to detect paper sections by looking for title-like lines
    # followed by author+affiliation lines
    i = 0
    in_paper = False
    first_aff_found = False
    paper_cn = False

    for line in lines:
        line = line.strip()
        if not line:
            if in_paper and first_aff_found:
                total_count += 1
                if paper_cn:
                    cn_count += 1
                in_paper = False
                first_aff_found = False
                paper_cn = False
            continue

        # Detect if this looks like a Chinese affiliation
        if is_chinese_institution(line):
            if not first_aff_found:
                paper_cn = True
            first_aff_found = True
            in_paper = True
        elif any(kw in line.lower() for kw in [
            "university", "institute", "lab ", "laboratory",
            "college", "department", "school of", "research center",
            "corp", "inc.", "ltd", "gmbh", "s.a.", "technology",
        ]):
            if not first_aff_found:
                first_aff_found = True
                in_paper = True

    return total_count, cn_count


def analyze_page_content(content: str, conf_name: str) -> dict:
    """
    Analyze page content to extract Chinese institution statistics.
    Uses multiple heuristics depending on what's in the content.
    """
    total, cn = count_chinese_from_text(content)

    # Backup heuristic: count Chinese keyword occurrences
    cn_mentions = len(CN_PATTERN.findall(content))

    return {
        "raw_length": len(content),
        "total_papers_detected": total,
        "cn_first_author_detected": cn,
        "cn_keyword_mentions": cn_mentions,
    }


def process_conference(browser, name: str, conf: dict) -> dict:
    """Process a single conference."""
    strategy = conf["strategy"]
    url = conf["url"]
    year = conf["year"]

    print(f"  [{strategy}] {url[:70]}", end="", flush=True)

    context = browser.new_context(
        user_agent="Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
    )
    page = context.new_page()

    try:
        scraper = SCRAPERS.get(strategy, scrape_generic_list)
        papers = scraper(page, url)

        # Combine all content
        full_content = "\n".join(
            (p.get("title", "") + "\n" + p.get("context", "")) for p in papers
        )

        # Save raw content for debugging
        raw_file = f"/home/nanogpt/prj/ccf-conference/raw/{name.replace('/', '_').replace(' ', '_')}_{year}.txt"
        os.makedirs(os.path.dirname(raw_file), exist_ok=True)
        with open(raw_file, "w", encoding="utf-8") as f:
            f.write(full_content[:50000])  # cap at 50KB

        stats = analyze_page_content(full_content, name)
        print(f" -> {len(full_content)} chars, {stats['cn_keyword_mentions']} CN mentions")

        return {
            "name": name,
            "year": year,
            "url": url,
            "strategy": strategy,
            "raw_length": stats["raw_length"],
            "cn_keyword_mentions": stats["cn_keyword_mentions"],
            "error": None,
        }

    except Exception as e:
        print(f" -> ERROR: {e}")
        return {
            "name": name,
            "year": year,
            "url": url,
            "strategy": strategy,
            "error": str(e),
        }
    finally:
        context.close()


def main():
    results = []
    total = len(CONFERENCES)
    print(f"Scraping {total} conference program pages with Playwright (headless Chromium)")
    print("=" * 80)

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)

        for i, (name, conf) in enumerate(CONFERENCES.items()):
            print(f"[{i+1}/{total}] {name} ({conf['year']}):", end=" ", flush=True)
            result = process_conference(browser, name, conf)
            results.append(result)
            time.sleep(1)  # polite delay

        browser.close()

    # Summary
    ok = [r for r in results if not r.get("error")]
    err = [r for r in results if r.get("error")]
    print(f"\n{'='*80}")
    print(f"Done: {len(ok)} succeeded, {len(err)} failed")
    if err:
        print("Failed:", [r["name"] for r in err])

    # Save results
    out = "/home/nanogpt/prj/ccf-conference/browser_scrape_results.json"
    with open(out, "w", encoding="utf-8") as f:
        json.dump(results, f, ensure_ascii=False, indent=2)
    print(f"Results saved to {out}")
    print(f"Raw page content saved to /home/nanogpt/prj/ccf-conference/raw/")


if __name__ == "__main__":
    main()
