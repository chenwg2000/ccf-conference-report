#!/usr/bin/env python3
"""
Fix-up script for conferences that need alternative DBLP keys.
Handles multi-volume proceedings and journal-based publishing models.
DBLP rate limit: 1.5s between requests.
"""

import requests
import time
import json
import os
import sys

# Import Chinese name detection from main script
sys.path.insert(0, os.path.dirname(__file__))
from scrape_dblp import is_likely_chinese_name


def fetch_papers(query: str, max_pages: int = 10) -> list:
    """Fetch all papers matching a DBLP TOC query with pagination."""
    all_papers = []
    hits_per_page = 1000

    for page in range(max_pages):
        url = "https://dblp.org/search/publ/api"
        params = {
            "q": query,
            "format": "json",
            "h": hits_per_page,
            "f": page * hits_per_page,
        }
        r = requests.get(url, params=params, timeout=60)
        r.raise_for_status()
        data = r.json()

        hits = data.get("result", {}).get("hits", {})
        total = int(hits.get("@total", 0))
        hit_list = hits.get("hit", [])

        if not hit_list:
            break

        for h in hit_list:
            info = h.get("info", {})
            authors_info = info.get("authors", {})
            author_list = authors_info.get("author", [])
            if isinstance(author_list, dict):
                author_list = [author_list]

            authors = []
            for a in author_list:
                if isinstance(a, dict):
                    authors.append(a.get("text", a.get("#text", "")))
                elif isinstance(a, str):
                    authors.append(a)

            all_papers.append({
                "title": info.get("title", ""),
                "first_author": authors[0] if authors else "",
            })

        fetched = (page + 1) * hits_per_page
        if fetched >= total:
            break

        time.sleep(1.5)

    return all_papers


def process_queries(name: str, queries: list) -> dict:
    """Process multiple queries for a single conference (multi-volume)."""
    print(f"  Fetching {name}...", end="", flush=True)
    all_papers = []
    for q in queries:
        try:
            papers = fetch_papers(q)
            all_papers.extend(papers)
            time.sleep(1.5)
        except Exception as e:
            print(f" (error on query: {e})", end="")

    chinese_count = sum(1 for p in all_papers if is_likely_chinese_name(p["first_author"]))
    total = len(all_papers)
    pct = round(chinese_count / max(total, 1) * 100, 1)
    print(f" {total} papers, {chinese_count} CN first-author (~{pct}%)")

    return {
        "name": name,
        "total_papers": total,
        "chinese_first_author": chinese_count,
        "chinese_pct": pct,
    }


# Conferences needing fixes with their DBLP TOC queries
FIXUPS = {
    # Multi-volume proceedings
    "ASPLOS": [
        "toc:db/conf/asplos/asplos2025-1.bht:",
        "toc:db/conf/asplos/asplos2025-2.bht:",
        "toc:db/conf/asplos/asplos2025-3.bht:",
    ],
    "EUROCRYPT": [
        f"toc:db/conf/eurocrypt/eurocrypt2025-{i}.bht:" for i in range(1, 9)
    ],
    "CRYPTO": [
        f"toc:db/conf/crypto/crypto2024-{i}.bht:" for i in range(1, 11)
    ],
    "CAV": [
        "toc:db/conf/cav/cav2025-1.bht:",
        "toc:db/conf/cav/cav2025-2.bht:",
        "toc:db/conf/cav/cav2025-3.bht:",
        "toc:db/conf/cav/cav2025-4.bht:",
    ],
    "FM": [
        "toc:db/conf/fm/fm2024-1.bht:",
        "toc:db/conf/fm/fm2024-2.bht:",
    ],
    "ACL": [
        f"toc:db/conf/acl/acl2025-{i}.bht:" for i in range(1, 5)
    ],

    # NeurIPS 2024 (single large volume)
    "NeurIPS": [
        "toc:db/conf/nips/neurips2024.bht:",
    ],

    # Journal-based publishing model
    "SIGMOD": [
        "toc:db/journals/pacmmod/pacmmod3.bht:",
    ],
    "VLDB": [
        "toc:db/journals/pvldb/pvldb18.bht:",
    ],
    "UbiComp": [
        "toc:db/journals/imwut/imwut8.bht:",
    ],

    # Different DBLP key
    "ASE": [
        "toc:db/conf/kbse/ase2024.bht:",
    ],
    "ACM MM": [
        "toc:db/conf/mm/mm2024.bht:",
    ],

    # OOPSLA publishes via PACMPL
    "OOPSLA": [
        "toc:db/journals/pacmpl/pacmpl8-OOPSLA1.bht:",
        "toc:db/journals/pacmpl/pacmpl8-OOPSLA2.bht:",
    ],
    "POPL": [
        "toc:db/journals/pacmpl/pacmpl9-POPL.bht:",
    ],
    "PLDI": [
        "toc:db/journals/pacmpl/pacmpl9-PLDI.bht:",
    ],
    "ISSTA": [
        "toc:db/journals/pacmse/pacmse1-ISSTA.bht:",
    ],
    "FSE": [
        "toc:db/journals/pacmse/pacmse1-FSE.bht:",
        "toc:db/journals/pacmse/pacmse2-FSE.bht:",
    ],

    # CSCW publishes via PACM HCI
    "CSCW": [
        "toc:db/journals/pacmhci/pacmhci8-CSCW1.bht:",
        "toc:db/journals/pacmhci/pacmhci8-CSCW2.bht:",
    ],

    # KDD 2025
    "SIGKDD": [
        "toc:db/conf/kdd/kdd2025-1.bht:",
        "toc:db/conf/kdd/kdd2025-2.bht:",
        "toc:db/conf/kdd/kdd2025.bht:",
    ],

    # ICCV 2025 (biennial, may not be on DBLP yet)
    "ICCV": [
        "toc:db/conf/iccv/iccv2025.bht:",
    ],
}


def main():
    results = {}
    total = len(FIXUPS)
    print(f"Processing {total} fix-up conferences (1.5s rate limit)")
    print("=" * 70)

    for i, (name, queries) in enumerate(FIXUPS.items()):
        print(f"[{i+1}/{total}]", end="")
        result = process_queries(name, queries)
        results[name] = result

    print("\n" + "=" * 70)
    print("FIX-UP RESULTS")
    print("=" * 70)
    print(f"{'Conference':<18} {'Total':<8} {'CN 1st':<10} {'CN %':<8}")
    print("-" * 44)
    for name, r in results.items():
        print(f"{name:<18} {r['total_papers']:<8} {r['chinese_first_author']:<10} {r['chinese_pct']:.1f}%")

    # Save fix-up results
    output_path = os.path.join(os.path.dirname(__file__), "chinese_first_author_fixup.json")
    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(results, f, ensure_ascii=False, indent=2)
    print(f"\nFix-up results saved to {output_path}")


if __name__ == "__main__":
    main()
