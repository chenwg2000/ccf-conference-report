#!/usr/bin/env python3
"""
Scrape DBLP for CCF A-class conference papers and estimate
Chinese first-author paper counts using surname heuristics.

DBLP rate limit: ~1 request per second (we use 1.5s to be safe).
"""

import requests
import time
import json
import sys
import os

# Common Chinese surnames in pinyin (covers ~95% of Chinese population)
CHINESE_SURNAMES = {
    # Top 100+ most common Chinese surnames
    "wang", "li", "zhang", "liu", "chen", "yang", "zhao", "huang", "zhou", "wu",
    "xu", "sun", "hu", "zhu", "gao", "lin", "he", "guo", "ma", "luo",
    "liang", "song", "zheng", "xie", "han", "tang", "feng", "yu", "dong", "xiao",
    "cheng", "cao", "yuan", "deng", "xu", "fu", "shen", "zeng", "peng", "lu",
    "su", "jiang", "cai", "jia", "ding", "wei", "xue", "ye", "yan", "pan",
    "du", "dai", "xia", "zhong", "wang", "tian", "ren", "fan", "shi", "liao",
    "gu", "qian", "kong", "bai", "cui", "kang", "mao", "qiu", "qin", "wen",
    "niu", "hao", "shao", "long", "wan", "tan", "jin", "duan", "lei", "hou",
    "meng", "xiong", "bao", "chang", "weng", "lai", "chu", "ning", "zou",
    "zhuang", "ji", "shan", "lan", "min", "yin", "yao", "lv", "bi", "he",
    "nie", "qi", "pei", "ren", "hua", "you", "mu", "hong", "tao",
    # Additional common ones
    "ai", "an", "ban", "bei", "bian", "cang", "che", "chi", "chong",
    "diao", "fang", "ge", "geng", "gong", "hang", "heng", "jiao",
    "ke", "kuang", "lang", "leng", "ling", "mei", "mi", "mo", "nong",
    "ou", "ping", "pu", "qiao", "rong", "ruan", "sang", "shang",
    "shu", "si", "sui", "tie", "tong", "tu", "wa", "wen", "xi",
    "xiang", "xin", "xing", "yue", "yun", "zhan", "zhi", "zhuo",
}

# Two-character Chinese surnames in pinyin
CHINESE_DOUBLE_SURNAMES = {
    "ouyang", "shangguan", "situ", "linghu", "huangfu", "zhuge",
    "dongfang", "nangong", "xiahou", "murong", "duanmu", "gongsun",
}


def is_likely_chinese_name(name: str) -> bool:
    """
    Heuristic to check if a name is likely Chinese based on surname.
    Format from DBLP is typically "Firstname Lastname" or "Firstname M. Lastname".
    Chinese names on DBLP are usually "Pinyin-Given Surname" or "Given Surname".
    """
    if not name:
        return False

    parts = name.strip().split()
    if len(parts) < 2:
        return False

    # Last word is typically the surname in Western order,
    # but DBLP sometimes uses "Surname, Firstname" format too
    # Try last name first (most common on DBLP)
    last = parts[-1].lower().rstrip(".")

    if last in CHINESE_SURNAMES:
        return True

    # Check double surnames
    if len(parts) >= 2:
        potential_double = parts[-1].lower()
        if potential_double in CHINESE_DOUBLE_SURNAMES:
            return True

    # Also check first word (in case of "Surname Firstname" format)
    first = parts[0].lower().rstrip(",")
    if first in CHINESE_SURNAMES and len(parts) <= 3:
        # Only if the name is short (Chinese names are typically 2-3 parts)
        return True

    return False


# Conference DBLP keys: (dblp_conf_key, year, alt_key)
# dblp_conf_key maps to dblp.org/db/conf/{key}/{key}{year}.html
CONFERENCES = [
    # Area 1: Computer Architecture
    ("ppopp", 2025, "PPoPP"),
    ("fast", 2025, "FAST"),
    ("dac", 2025, "DAC"),
    ("hpca", 2025, "HPCA"),
    ("micro", 2024, "MICRO"),
    ("sc", 2024, "SC"),
    ("asplos", 2025, "ASPLOS"),
    ("isca", 2025, "ISCA"),
    ("usenix", 2025, "USENIX ATC"),  # ATC uses /conf/usenix/
    ("eurosys", 2025, "EuroSys"),
    ("hpdc", 2025, "HPDC"),

    # Area 2: Computer Networks
    ("sigcomm", 2025, "SIGCOMM"),
    ("mobicom", 2024, "MobiCom"),
    ("infocom", 2025, "INFOCOM"),
    ("nsdi", 2025, "NSDI"),

    # Area 3: Security
    ("ccs", 2024, "CCS"),
    ("eurocrypt", 2025, "EUROCRYPT"),
    ("sp", 2025, "S&P"),
    ("crypto", 2024, "CRYPTO"),
    ("uss", 2025, "USENIX Security"),  # USENIX Security uses /conf/uss/
    ("ndss", 2025, "NDSS"),

    # Area 4: Software Engineering
    ("pldi", 2025, "PLDI"),
    ("popl", 2025, "POPL"),
    ("sigsoft", 2025, "FSE"),  # FSE uses /conf/sigsoft/
    ("sosp", 2024, "SOSP"),
    ("oopsla", 2024, "OOPSLA"),
    ("kbse", 2024, "ASE"),  # ASE uses /conf/kbse/
    ("icse", 2025, "ICSE"),
    ("issta", 2025, "ISSTA"),
    ("osdi", 2024, "OSDI"),
    ("fm", 2024, "FM"),

    # Area 5: Database/Data Mining
    ("sigmod", 2025, "SIGMOD"),
    ("kdd", 2025, "SIGKDD"),
    ("icde", 2025, "ICDE"),
    ("sigir", 2025, "SIGIR"),
    ("vldb", 2025, "VLDB"),

    # Area 6: Theory
    ("stoc", 2025, "STOC"),
    ("soda", 2025, "SODA"),
    ("cav", 2025, "CAV"),
    ("focs", 2024, "FOCS"),
    ("lics", 2025, "LICS"),

    # Area 7: Graphics/Multimedia
    ("mm", 2024, "ACM MM"),
    ("siggraph", 2025, "SIGGRAPH"),
    ("vr", 2025, "VR"),
    ("visualization", 2024, "IEEE VIS"),

    # Area 8: AI
    ("aaai", 2025, "AAAI"),
    ("nips", 2024, "NeurIPS"),
    ("acl", 2025, "ACL"),
    ("cvpr", 2025, "CVPR"),
    ("iccv", 2025, "ICCV"),
    ("icml", 2025, "ICML"),
    ("iclr", 2025, "ICLR"),

    # Area 9: HCI
    ("cscw", 2024, "CSCW"),
    ("chi", 2025, "CHI"),
    ("huc", 2024, "UbiComp"),  # UbiComp uses /conf/huc/
    ("uist", 2024, "UIST"),

    # Area 10: Interdisciplinary
    ("www", 2025, "WWW"),
    ("rtss", 2024, "RTSS"),
]


def fetch_dblp_toc(conf_key: str, year: int, page: int = 0, hits_per_page: int = 1000) -> dict:
    """Fetch proceedings from DBLP using the TOC search API."""
    # Try the standard TOC query
    query = f"toc:db/conf/{conf_key}/{conf_key}{year}.bht:"
    url = "https://dblp.org/search/publ/api"
    params = {
        "q": query,
        "format": "json",
        "h": hits_per_page,
        "f": page * hits_per_page,
    }
    r = requests.get(url, params=params, timeout=60)
    r.raise_for_status()
    return r.json()


def fetch_all_papers(conf_key: str, year: int) -> list:
    """Fetch all papers for a conference, handling pagination."""
    all_papers = []
    page = 0
    hits_per_page = 1000

    while True:
        data = fetch_dblp_toc(conf_key, year, page, hits_per_page)
        result = data.get("result", {})
        hits = result.get("hits", {})
        total = int(hits.get("@total", 0))

        if total == 0:
            break

        hit_list = hits.get("hit", [])
        if not hit_list:
            break

        for h in hit_list:
            info = h.get("info", {})
            authors_info = info.get("authors", {})
            author_list = authors_info.get("author", [])

            # author_list can be a single dict or a list
            if isinstance(author_list, dict):
                author_list = [author_list]

            authors = []
            for a in author_list:
                if isinstance(a, dict):
                    authors.append(a.get("text", a.get("#text", "")))
                elif isinstance(a, str):
                    authors.append(a)

            title = info.get("title", "")
            all_papers.append({
                "title": title,
                "authors": authors,
                "first_author": authors[0] if authors else "",
            })

        # Check if we need more pages
        fetched = (page + 1) * hits_per_page
        if fetched >= total:
            break

        page += 1
        time.sleep(1.5)  # Rate limit

    return all_papers


def process_conference(conf_key: str, year: int, display_name: str) -> dict:
    """Process a single conference and return statistics."""
    print(f"  Fetching {display_name} ({conf_key}/{year})...", end="", flush=True)

    try:
        papers = fetch_all_papers(conf_key, year)
    except Exception as e:
        print(f" ERROR: {e}")
        return {
            "name": display_name,
            "key": conf_key,
            "year": year,
            "total_papers": 0,
            "chinese_first_author": 0,
            "error": str(e),
        }

    chinese_count = 0
    chinese_authors = []
    for p in papers:
        if is_likely_chinese_name(p["first_author"]):
            chinese_count += 1
            chinese_authors.append(p["first_author"])

    print(f" {len(papers)} papers, {chinese_count} Chinese first-author (~{chinese_count/max(len(papers),1)*100:.1f}%)")

    return {
        "name": display_name,
        "key": conf_key,
        "year": year,
        "total_papers": len(papers),
        "chinese_first_author": chinese_count,
        "chinese_pct": round(chinese_count / max(len(papers), 1) * 100, 1),
        "error": None,
    }


def main():
    results = []
    total = len(CONFERENCES)

    print(f"Processing {total} conferences (DBLP rate limit: 1.5s between requests)")
    print("=" * 80)

    for i, (conf_key, year, display_name) in enumerate(CONFERENCES):
        print(f"[{i+1}/{total}]", end="")
        result = process_conference(conf_key, year, display_name)
        results.append(result)
        # Rate limit between conferences
        if i < total - 1:
            time.sleep(1.5)

    print("\n" + "=" * 80)
    print("RESULTS SUMMARY")
    print("=" * 80)
    print(f"{'Conference':<18} {'Year':<6} {'Total':<8} {'CN 1st Author':<14} {'CN %':<8}")
    print("-" * 54)

    for r in results:
        if r["error"]:
            print(f"{r['name']:<18} {r['year']:<6} {'ERR':<8} {'N/A':<14} {'N/A':<8}")
        else:
            print(f"{r['name']:<18} {r['year']:<6} {r['total_papers']:<8} {r['chinese_first_author']:<14} {r['chinese_pct']:.1f}%")

    # Save to JSON
    output_path = os.path.join(os.path.dirname(__file__), "chinese_first_author_stats.json")
    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(results, f, ensure_ascii=False, indent=2)
    print(f"\nResults saved to {output_path}")


if __name__ == "__main__":
    main()
