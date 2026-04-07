#!/usr/bin/env python3
"""
Pipeline: DBLP → arXiv search → arXiv HTML affiliations
All network calls via Playwright browser (confirmed working).

Rate limits:
  DBLP search API: 2s between requests
  arXiv search API: 4s between requests  (polite rate limit)
  arXiv HTML pages: 3s between page loads
"""

import re, time, json, os, random
import xml.etree.ElementTree as ET
from playwright.sync_api import sync_playwright

# ── Chinese institution keywords ─────────────────────────────────────────────
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
    "shenzhen", "guangzhou", "hangzhou", "hefei",
    "hong kong", "hkust", " hku ", "hku,", "cuhk", "cityu", "polyu",
    "chinese university of hong kong",
    "macau", "macao", "taiwan", "academia sinica",
]

def is_cn(affil):
    if not affil: return False
    return any(k in affil.lower() for k in CN_KW)


# ── DBLP via Playwright ───────────────────────────────────────────────────────
def dblp_fetch(page, query):
    import urllib.parse
    papers, offset = [], 0
    while True:
        url = (f"https://dblp.org/search/publ/api"
               f"?q={urllib.parse.quote(query)}&format=json&h=1000&f={offset}")
        try:
            page.goto(url, timeout=30000)
            time.sleep(2)
            data = json.loads(page.inner_text("body"))
        except Exception as e:
            print(f"    DBLP error: {e}")
            break
        hits = data.get("result", {}).get("hits", {})
        total = int(hits.get("@total", 0))
        if total == 0: break
        hit_list = hits.get("hit", [])
        if not hit_list: break
        for h in hit_list:
            info = h.get("info", {})
            al = info.get("authors", {}).get("author", [])
            if isinstance(al, dict): al = [al]
            authors = [a.get("text", a.get("#text", ""))
                       if isinstance(a, dict) else a for a in al]
            papers.append({
                "title": info.get("title", "").rstrip("."),
                "first_author": re.sub(r'\s+\d{4}$', '', authors[0]).strip() if authors else "",
            })
        offset += len(hit_list)
        if offset >= total: break
    return papers


# ── arXiv search (API → XML) ──────────────────────────────────────────────────
ARXIV_NS   = "http://www.w3.org/2005/Atom"

def arxiv_find_id(page, title, author):
    import urllib.parse
    clean = re.sub(r'[^\w\s]', ' ', title)[:70].strip()
    q = urllib.parse.quote(f'ti:"{clean}"')
    url = f"https://export.arxiv.org/api/query?search_query={q}&max_results=3"
    try:
        page.goto(url, timeout=25000)
        time.sleep(4)
        root = ET.fromstring(page.inner_text("body"))
        entries = root.findall(f"{{{ARXIV_NS}}}entry")
        if not entries: return None
        al = author.split()[-1].lower() if author else ""
        for e in entries:
            fa_el = e.findall(f"{{{ARXIV_NS}}}author")
            if fa_el and al and al in fa_el[0].findtext(f"{{{ARXIV_NS}}}name","").lower():
                m = re.search(r'abs/(.+?)(?:v\d+)?$',
                              e.findtext(f"{{{ARXIV_NS}}}id",""))
                return m.group(1).strip() if m else None
        # fallback: first result
        m = re.search(r'abs/(.+?)(?:v\d+)?$',
                      entries[0].findtext(f"{{{ARXIV_NS}}}id",""))
        return m.group(1).strip() if m else None
    except Exception:
        return None


# ── arXiv HTML page affiliation parser ────────────────────────────────────────
INST_KW = ["university","institute","lab","school","college","research",
           "corp","tech","science","computer","center","dept","department",
           "faculty","academy","hospital","foundation","company","group"]

def arxiv_html_affil(page, arxiv_id):
    try:
        page.goto(f"https://arxiv.org/html/{arxiv_id}", timeout=25000)
        time.sleep(3)
        text = page.inner_text("body")
        lines = [l.strip() for l in text.split("\n") if l.strip()]

        # Find Abstract. boundary
        abs_i = next((i for i,l in enumerate(lines)
                      if re.match(r'^abstract\.?', l.lower())), len(lines))
        header = lines[:min(abs_i, 100)]

        # Find first non-nav line that looks like an author name
        nav_kw = {"back to","arxiv:","report issue","download","learn more",
                  "license:","access paper","submission history","cite as",
                  "why html","toggle","use alt"}
        first_author_idx = None
        for i, l in enumerate(header):
            if i < 3: continue
            if any(n in l.lower() for n in nav_kw): continue
            words = l.split()
            if (2 <= len(words) <= 5
                    and all(w[0].isupper() for w in words if w.isalpha())
                    and not any(c.isdigit() for c in l)
                    and not any(k in l.lower() for k in INST_KW)):
                first_author_idx = i
                break

        if first_author_idx is None: return None

        # Collect affiliation lines after first author name
        affil_parts = []
        for l in header[first_author_idx+1:first_author_idx+6]:
            words = l.split()
            # Stop if looks like another author (short, title-case, no inst kw)
            if (2 <= len(words) <= 5
                    and all(w[0].isupper() for w in words if w.isalpha())
                    and not any(c.isdigit() for c in l)
                    and not any(k in l.lower() for k in INST_KW)):
                break
            if l and len(l) < 120:
                affil_parts.append(l)
        return ", ".join(affil_parts[:3]) if affil_parts else None
    except Exception:
        return None


# ── Conferences ───────────────────────────────────────────────────────────────
CONFERENCES = [
    # Small/medium systems & theory
    ("HPCA",    2025, ["toc:db/conf/hpca/hpca2025.bht:"]),
    ("SC",      2024, ["toc:db/conf/sc/sc2024.bht:"]),
    ("ISCA",    2025, ["toc:db/conf/isca/isca2025.bht:"]),
    ("HPDC",    2025, ["toc:db/conf/hpdc/hpdc2025.bht:"]),
    ("LICS",    2025, ["toc:db/conf/lics/lics2025.bht:"]),
    ("RTSS",    2024, ["toc:db/conf/rtss/rtss2024.bht:"]),
    ("VR",      2025, ["toc:db/conf/vr/vr2025.bht:"]),
    ("IEEE VIS",2024, ["toc:db/conf/visualization/vis2024.bht:"]),
    ("UIST",    2024, ["toc:db/conf/uist/uist2024.bht:"]),
    ("UbiComp", 2024, ["toc:db/journals/imwut/imwut8.bht:"]),
    # Larger conferences (will be sampled)
    ("CHI",     2025, ["toc:db/conf/chi/chi2025.bht:"]),
    ("SIGMOD",  2025, ["toc:db/journals/pacmmod/pacmmod3.bht:"]),
    ("VLDB",    2025, ["toc:db/journals/pvldb/pvldb18.bht:"]),
    ("SIGIR",   2025, ["toc:db/conf/sigir/sigir2025.bht:"]),
    ("WWW",     2025, ["toc:db/conf/www/www2025.bht:"]),
    ("SIGKDD",  2025, ["toc:db/conf/kdd/kdd2025-1.bht:",
                       "toc:db/conf/kdd/kdd2025-2.bht:"]),
    # Large AI (sampled, many arXiv preprints)
    ("NeurIPS", 2024, ["toc:db/conf/nips/neurips2024.bht:"]),
    ("AAAI",    2025, ["toc:db/conf/aaai/aaai2025.bht:"]),
    ("ACL",     2025, ["toc:db/conf/acl/acl2025-1.bht:",
                       "toc:db/conf/acl/acl2025-2.bht:",
                       "toc:db/conf/acl/acl2025-3.bht:"]),
    ("CVPR",    2025, ["toc:db/conf/cvpr/cvpr2025.bht:"]),
    ("ICCV",    2023, ["toc:db/conf/iccv/iccv2023.bht:"]),
    ("ICML",    2025, ["toc:db/conf/icml/icml2025.bht:"]),
    ("ICLR",    2025, ["toc:db/conf/iclr/iclr2025.bht:"]),
]

SAMPLE = {"NeurIPS":300,"AAAI":300,"CVPR":300,"ICML":300,"ICLR":300,
          "ACL":200,"ICCV":300,"CHI":200,"SIGKDD":200,"SIGIR":150,
          "VLDB":150,"SIGMOD":150,"WWW":150}

OUTPUT = os.path.join(os.path.dirname(__file__), "arxiv_affil_results.json")


def process(page, name, year, queries):
    print(f"\n{'='*72}\n  {name} ({year})\n{'='*72}")

    papers = []
    for q in queries:
        papers.extend(dblp_fetch(page, q))
    print(f"  DBLP: {len(papers)} papers")
    if not papers:
        return {"name":name,"year":year,"total_dblp":0,"cn_in_sample":0,"cn_pct":0.0}

    max_n = SAMPLE.get(name, 9999)
    sampled = len(papers) > max_n
    sample = random.sample(papers, max_n) if sampled else papers
    if sampled: print(f"  Sample: {max_n}/{len(papers)}")

    cn = arxiv_ok = 0
    recs = []
    for i, p in enumerate(sample):
        t, a = p["title"], p["first_author"]
        aid = arxiv_find_id(page, t, a)
        affil = arxiv_html_affil(page, aid) if aid else None
        flag = is_cn(affil)
        if aid:  arxiv_ok += 1
        if flag: cn += 1
        tag = "✓CN" if flag else ("   " if affil else "N/A")
        print(f"  [{i+1:4d}/{len(sample)}] {tag} | {a[:22]:<22} | "
              f"{(affil or 'not on arXiv')[:52]}")
        recs.append({"a":a,"id":aid,"affil":affil or "","cn":flag})
        if (i+1) % 25 == 0:
            _save(name, year, len(papers), sample, recs, cn, arxiv_ok, sampled)

    pct = round(cn / max(len(sample),1) * 100, 1)
    hit = round(arxiv_ok / max(len(sample),1) * 100, 1)
    print(f"\n  → total={len(papers)}, sample={len(sample)}, "
          f"CN={cn} ({pct}%), arXiv={hit}%")
    return {"name":name,"year":year,"total_dblp":len(papers),
            "sample_size":len(sample),"cn_in_sample":cn,"cn_pct":pct,
            "arxiv_found":arxiv_ok,"hit_pct":hit,"sampled":sampled,"papers":recs}


def _save(name, year, total, sample, recs, cn, arxiv_ok, sampled):
    existing = json.load(open(OUTPUT)) if os.path.exists(OUTPUT) else []
    existing = [r for r in existing if r.get("name") != name]
    existing.append({
        "name":name,"year":year,"total_dblp":total,
        "sample_size":len(sample),"cn_in_sample":cn,
        "cn_pct":round(cn/max(len(recs),1)*100,1),
        "arxiv_found":arxiv_ok,"sampled":sampled,
        "_partial":True,"papers_so_far":recs
    })
    with open(OUTPUT,"w") as f:
        json.dump(existing, f, ensure_ascii=False, indent=2)


def main():
    random.seed(42)
    all_res = json.load(open(OUTPUT)) if os.path.exists(OUTPUT) else []
    done = {r["name"] for r in all_res if not r.get("_partial")}
    print(f"Done: {sorted(done)}")

    with sync_playwright() as pw:
        browser = pw.chromium.launch(headless=True)
        page = browser.new_page()
        page.set_extra_http_headers({"User-Agent":
            "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
            "Chrome/120.0.0.0 Safari/537.36"})

        for name, year, queries in CONFERENCES:
            if name in done:
                print(f"  Skip {name}")
                continue
            try:
                res = process(page, name, year, queries)
                all_res = [r for r in all_res if r.get("name") != name]
                all_res.append(res)
                with open(OUTPUT,"w") as f:
                    json.dump(all_res, f, ensure_ascii=False, indent=2)
            except KeyboardInterrupt:
                print("\nInterrupted.")
                break
            except Exception as e:
                print(f"  ERR {name}: {e}")
                all_res.append({"name":name,"year":year,"error":str(e),"cn_pct":0})
                with open(OUTPUT,"w") as f:
                    json.dump(all_res, f, ensure_ascii=False, indent=2)

        browser.close()

    print("\n" + "="*72)
    print(f"{'Conf':<12} {'Total':>7} {'Sample':>7} {'CN%':>7} {'arXiv%':>8}")
    for r in all_res:
        s = "*" if r.get("sampled") else " "
        err = r.get("error","")
        if err:
            print(f"{r['name']:<12} ERROR: {err[:40]}")
        else:
            print(f"{r['name']:<12}{s} {r.get('total_dblp',0):>6} "
                  f"{r.get('sample_size',r.get('total_dblp',0)):>7} "
                  f"{r.get('cn_pct',0):>6.1f}% "
                  f"{r.get('hit_pct',0):>7.1f}%")


if __name__ == "__main__":
    main()
