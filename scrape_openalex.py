#!/usr/bin/env python3
"""
Use OpenAlex API to count Chinese first-author papers for CCF A-class conferences.
"Chinese first-author" = first author's institution country_code is "CN".

OpenAlex polite pool: include email in User-Agent, rate limit ~10 req/s.
We use 0.2s delay (5 req/s) to be safe.
"""

import requests
import time
import json
import os
import sys

HEADERS = {"User-Agent": "CCFReport/1.0 (mailto:ccf-research@example.com)"}
BASE_URL = "https://api.openalex.org"
DELAY = 0.2  # seconds between requests (polite pool allows ~10/s)


def find_source_id(search_term: str) -> str | None:
    """Find the OpenAlex source ID for a conference/journal."""
    url = f"{BASE_URL}/sources"
    params = {"search": search_term, "per_page": 5, "select": "id,display_name,type"}
    r = requests.get(url, params=params, timeout=120, headers=HEADERS)
    r.raise_for_status()
    results = r.json().get("results", [])
    for s in results:
        # Prefer conference type, but accept journal too
        if s.get("type") == "conference":
            return s["id"].split("/")[-1]
    # Fall back to first result
    if results:
        return results[0]["id"].split("/")[-1]
    return None


def count_chinese_first_author(source_id: str, year: int) -> dict:
    """
    Count papers where the first author's institution is in China.
    Uses OpenAlex pagination with cursor.
    """
    total_papers = 0
    cn_first_author = 0
    no_affiliation = 0
    cursor = "*"

    while cursor:
        url = f"{BASE_URL}/works"
        params = {
            "filter": f"primary_location.source.id:{source_id},publication_year:{year}",
            "per_page": 200,
            "cursor": cursor,
            "select": "id,authorships",
        }
        try:
            r = requests.get(url, params=params, timeout=120, headers=HEADERS)
            r.raise_for_status()
        except Exception as e:
            print(f" [API error: {e}]", end="")
            break

        data = r.json()
        meta = data.get("meta", {})
        results = data.get("results", [])

        if not results:
            break

        for paper in results:
            total_papers += 1
            authorships = paper.get("authorships", [])
            if not authorships:
                no_affiliation += 1
                continue

            first_author = authorships[0]
            institutions = first_author.get("institutions", [])

            if not institutions:
                # Check countries field as fallback
                countries = first_author.get("countries", [])
                if "CN" in countries:
                    cn_first_author += 1
                else:
                    no_affiliation += 1
                continue

            # Check if any institution of first author is in China
            first_author_cn = any(
                inst.get("country_code") == "CN" for inst in institutions
            )
            if first_author_cn:
                cn_first_author += 1

        cursor = meta.get("next_cursor")
        time.sleep(DELAY)

    return {
        "total_papers": total_papers,
        "cn_first_author": cn_first_author,
        "no_affiliation": no_affiliation,
        "cn_pct": round(cn_first_author / max(total_papers, 1) * 100, 1),
    }


# Conference definitions: (display_name, search_term, year, alt_source_id)
# alt_source_id is used when search doesn't find the right source
CONFERENCES = [
    # Area 1: Computer Architecture
    ("PPoPP", "ACM SIGPLAN Symposium on Principles and Practice of Parallel Programming", 2025, None),
    ("FAST", "USENIX Conference on File and Storage Technologies", 2025, None),
    ("DAC", "Design Automation Conference", 2025, None),
    ("HPCA", "International Symposium on High-Performance Computer Architecture", 2025, None),
    ("MICRO", "International Symposium on Microarchitecture", 2024, None),
    ("SC", "International Conference for High Performance Computing Networking Storage and Analysis", 2024, None),
    ("ASPLOS", "International Conference on Architectural Support for Programming Languages and Operating Systems", 2025, None),
    ("ISCA", "International Symposium on Computer Architecture", 2025, None),
    ("USENIX ATC", "USENIX Annual Technical Conference", 2025, None),
    ("EuroSys", "European Conference on Computer Systems", 2025, None),
    ("HPDC", "International Symposium on High-Performance Parallel and Distributed Computing", 2025, None),

    # Area 2: Networks
    ("SIGCOMM", "ACM SIGCOMM Conference", 2025, None),
    ("MobiCom", "Annual International Conference on Mobile Computing and Networking", 2024, None),
    ("INFOCOM", "IEEE International Conference on Computer Communications", 2025, None),
    ("NSDI", "Symposium on Networked Systems Design and Implementation", 2025, None),

    # Area 3: Security
    ("CCS", "ACM Conference on Computer and Communications Security", 2024, None),
    ("EUROCRYPT", "International Conference on the Theory and Applications of Cryptographic Techniques", 2025, None),
    ("S&P", "IEEE Symposium on Security and Privacy", 2025, None),
    ("CRYPTO", "International Cryptology Conference", 2024, None),
    ("USENIX Security", "USENIX Security Symposium", 2025, None),
    ("NDSS", "Network and Distributed System Security Symposium", 2025, None),

    # Area 4: SE/PL
    ("PLDI", "ACM SIGPLAN Conference on Programming Language Design and Implementation", 2025, None),
    ("POPL", "ACM SIGPLAN-SIGACT Symposium on Principles of Programming Languages", 2025, None),
    ("FSE", "ACM Joint European Software Engineering Conference and Symposium on the Foundations of Software Engineering", 2024, None),
    ("SOSP", "ACM Symposium on Operating Systems Principles", 2024, None),
    ("OOPSLA", "Object-Oriented Programming Systems Languages and Applications", 2024, None),
    ("ASE", "International Conference on Automated Software Engineering", 2024, None),
    ("ICSE", "International Conference on Software Engineering", 2025, None),
    ("ISSTA", "International Symposium on Software Testing and Analysis", 2024, None),
    ("OSDI", "USENIX Symposium on Operating Systems Design and Implementation", 2024, None),
    ("FM", "International Symposium on Formal Methods", 2024, None),

    # Area 5: Database
    ("SIGMOD", "ACM SIGMOD International Conference on Management of Data", 2025, None),
    ("SIGKDD", "ACM SIGKDD International Conference on Knowledge Discovery and Data Mining", 2025, None),
    ("ICDE", "IEEE International Conference on Data Engineering", 2025, None),
    ("SIGIR", "ACM SIGIR Conference on Research and Development in Information Retrieval", 2025, None),
    ("VLDB", "International Conference on Very Large Data Bases", 2025, None),

    # Area 6: Theory
    ("STOC", "ACM Symposium on Theory of Computing", 2025, None),
    ("SODA", "ACM-SIAM Symposium on Discrete Algorithms", 2025, None),
    ("CAV", "International Conference on Computer Aided Verification", 2025, None),
    ("FOCS", "IEEE Symposium on Foundations of Computer Science", 2024, None),
    ("LICS", "ACM/IEEE Symposium on Logic in Computer Science", 2025, None),

    # Area 7: Graphics/Multimedia
    ("ACM MM", "ACM International Conference on Multimedia", 2024, None),
    ("SIGGRAPH", "ACM SIGGRAPH", 2025, None),
    ("VR", "IEEE Conference on Virtual Reality and 3D User Interfaces", 2025, None),
    ("IEEE VIS", "IEEE Visualization Conference", 2024, None),

    # Area 8: AI
    ("AAAI", "Proceedings of the AAAI Conference on Artificial Intelligence", 2025, "S4210191458"),
    ("NeurIPS", "Conference on Neural Information Processing Systems", 2024, None),
    ("ACL", "Annual Meeting of the Association for Computational Linguistics", 2025, None),
    ("CVPR", "IEEE/CVF Conference on Computer Vision and Pattern Recognition", 2025, None),
    ("ICCV", "IEEE/CVF International Conference on Computer Vision", 2023, None),
    ("ICML", "International Conference on Machine Learning", 2025, None),
    ("ICLR", "International Conference on Learning Representations", 2025, None),

    # Area 9: HCI
    ("CSCW", "ACM Conference on Computer-Supported Cooperative Work and Social Computing", 2024, None),
    ("CHI", "ACM CHI Conference on Human Factors in Computing Systems", 2025, None),
    ("UbiComp", "ACM International Joint Conference on Pervasive and Ubiquitous Computing", 2024, None),
    ("UIST", "ACM Symposium on User Interface Software and Technology", 2024, None),

    # Area 10: Interdisciplinary
    ("WWW", "The Web Conference", 2025, None),
    ("RTSS", "IEEE Real-Time Systems Symposium", 2024, None),
]


def main():
    results = []
    total = len(CONFERENCES)
    print(f"Processing {total} conferences via OpenAlex API (0.2s delay)")
    print("=" * 85)

    for i, (name, search_term, year, alt_id) in enumerate(CONFERENCES):
        print(f"[{i+1}/{total}] {name} ({year}):", end="", flush=True)

        # Find source ID
        if alt_id:
            source_id = alt_id
            print(f" (preset ID {source_id})", end="")
        else:
            print(f" searching...", end="", flush=True)
            try:
                source_id = find_source_id(search_term)
                time.sleep(DELAY)
            except Exception as e:
                print(f" search error: {e}")
                results.append({"name": name, "year": year, "error": str(e),
                               "total_papers": 0, "cn_first_author": 0, "cn_pct": 0})
                continue

        if not source_id:
            print(f" source not found!")
            results.append({"name": name, "year": year, "error": "source not found",
                           "total_papers": 0, "cn_first_author": 0, "cn_pct": 0})
            continue

        print(f" [{source_id}]", end="", flush=True)

        # Count papers
        try:
            stats = count_chinese_first_author(source_id, year)
        except Exception as e:
            print(f" count error: {e}")
            results.append({"name": name, "year": year, "source_id": source_id,
                           "error": str(e), "total_papers": 0, "cn_first_author": 0, "cn_pct": 0})
            continue

        stats["name"] = name
        stats["year"] = year
        stats["source_id"] = source_id
        stats["error"] = None
        results.append(stats)

        print(f" {stats['total_papers']} papers, {stats['cn_first_author']} CN ({stats['cn_pct']}%)"
              f" [no-aff: {stats['no_affiliation']}]")

    # Summary
    print("\n" + "=" * 85)
    print("RESULTS (Institution-based Chinese first-author count)")
    print("=" * 85)
    print(f"{'Conference':<18} {'Year':<6} {'Total':<8} {'CN Inst':<10} {'CN %':<8} {'No-aff':<8}")
    print("-" * 58)

    for r in results:
        if r.get("error"):
            print(f"{r['name']:<18} {r['year']:<6} {'ERR':<8} {'-':<10} {'-':<8} {'-':<8}")
        else:
            print(f"{r['name']:<18} {r['year']:<6} {r['total_papers']:<8} "
                  f"{r['cn_first_author']:<10} {r['cn_pct']:.1f}%   "
                  f"{r['no_affiliation']:<8}")

    # Save
    out = os.path.join(os.path.dirname(__file__), "chinese_institution_stats.json")
    with open(out, "w", encoding="utf-8") as f:
        json.dump(results, f, ensure_ascii=False, indent=2)
    print(f"\nSaved to {out}")


if __name__ == "__main__":
    main()
