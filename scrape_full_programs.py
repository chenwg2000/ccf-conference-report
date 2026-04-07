import time, re, json
from playwright.sync_api import sync_playwright

CN_KW = ['china','chinese','beijing','shanghai','tsinghua','peking','fudan',
         'zhejiang','nanjing','sjtu','wuhan','harbin','sun yat-sen','xjtu',
         'huawei','alibaba','tencent','bytedance','baidu','chinese academy',
         ' cas,', ' cas ','iscas','institute of software',
         'institute of computing technology','national university of defense',
         'ustc','nankai','tianjin','beihang','shenzhen','guangzhou','hangzhou',
         'xiamen','hong kong','hkust',' hku ','hku,','cuhk','cityu','polyu',
         'chinese university of hong kong','macau','taiwan','academia sinica']
def is_cn(s): return any(k in s.lower() for k in CN_KW) if s else False
BAD = ['http','www','201','202','room','floor','@','email']

def parse(text):
    lines = [l.strip() for l in text.split('\n') if l.strip()]
    papers = []
    seen = set()
    for i in range(1, len(lines)):
        line = lines[i]
        if '(' not in line or ')' not in line: continue
        prev = lines[i-1]
        if '(' in prev or len(prev) < 10: continue
        insts = [x for x in re.findall(r'\(([^)]{4,90})\)', line)
                 if not any(b in x.lower() for b in BAD)]
        if not insts: continue
        key = prev[:40]
        if key in seen: continue
        seen.add(key)
        papers.append({'t': prev[:60], 'affil': insts[0], 'cn': is_cn(insts[0])})
    return papers

def scroll_and_parse(page, url, name, max_scrolls=50, wait=4):
    print(f'\n{name}: {url}')
    try:
        page.goto(url, timeout=50000, wait_until='domcontentloaded')
        time.sleep(wait)
        prev_count = 0
        for i in range(max_scrolls):
            page.evaluate('window.scrollTo(0, document.body.scrollHeight)')
            time.sleep(1.5)
            text = page.inner_text('body')
            papers = parse(text)
            if len(papers) == prev_count and i > 5:
                break
            prev_count = len(papers)
        text = page.inner_text('body')
        papers = parse(text)
        cn = sum(1 for p in papers if p['cn'])
        pct = round(cn / max(len(papers), 1) * 100, 1)
        print(f'  {len(papers)} papers, {cn} CN ({pct}%)')
        return papers
    except Exception as e:
        print(f'  ERROR: {str(e)[:70]}')
        return []

all_results = {}

with sync_playwright() as pw:
    browser = pw.chromium.launch(headless=True)
    page = browser.new_page()
    page.set_extra_http_headers({'User-Agent': 'Mozilla/5.0 Chrome/120.0.0.0'})

    # ── SIGMOD full program page ───────────────────────────────────────────
    p1 = scroll_and_parse(page, 'https://2025.sigmod.org/program_full_detail.shtml',
                          'SIGMOD full program', max_scrolls=60)
    all_results['SIGMOD full program'] = p1

    # ── VLDB 2025 ─────────────────────────────────────────────────────────
    # VLDB papers are published in PVLDB journal; try the conference program
    for url, label in [
        ('https://vldb.org/2025/?program', 'VLDB program'),
        ('https://vldb.org/2025/?papers-research', 'VLDB research papers'),
    ]:
        p = scroll_and_parse(page, url, label, max_scrolls=30)
        all_results[label] = p

    # ── ISCA 2025 ─────────────────────────────────────────────────────────
    for url, label in [
        ('https://iscaconf.org/isca2025/program.php', 'ISCA program'),
        ('https://iscaconf.org/isca2025/', 'ISCA home'),
    ]:
        p = scroll_and_parse(page, url, label, max_scrolls=20, wait=6)
        all_results[label] = p

    # ── SC 2024 ───────────────────────────────────────────────────────────
    p_sc = scroll_and_parse(page, 'https://sc24.conference-program.com/',
                            'SC 2024 full program', max_scrolls=30, wait=6)
    all_results['SC 2024'] = p_sc

    # ── SIGKDD 2025 ───────────────────────────────────────────────────────
    for url, label in [
        ('https://kdd2025.kdd.org/accepted-papers/', 'KDD accepted'),
        ('https://kdd2025.kdd.org/program/', 'KDD program'),
    ]:
        p = scroll_and_parse(page, url, label, max_scrolls=20)
        all_results[label] = p

    # ── SIGIR 2025 ────────────────────────────────────────────────────────
    # SIGIR page format: Title, then author names (no affils) → check if
    # the program page is different
    for url, label in [
        ('https://sigir2025.dei.unipd.it/program.html', 'SIGIR program'),
        ('https://sigir2025.dei.unipd.it/', 'SIGIR home'),
    ]:
        p = scroll_and_parse(page, url, label, max_scrolls=20, wait=5)
        all_results[label] = p

    # ── LICS 2025 ─────────────────────────────────────────────────────────
    p_lics = scroll_and_parse(page, 'https://lics.siglog.org/lics25/accepted.php',
                              'LICS 2025', max_scrolls=10, wait=5)
    all_results['LICS 2025'] = p_lics

    browser.close()

# Summary
print('\n' + '='*60)
for name, papers in all_results.items():
    cn = sum(1 for p in papers if p['cn'])
    total = len(papers)
    pct = round(cn / max(total, 1) * 100, 1)
    print(f'{name:30} {total:5} papers  {cn:4} CN ({pct:.1f}%)')
    if total > 0:
        for p in papers:
            if p['cn']:
                print(f'  ✓ {p["affil"][:55]}')

with open('/home/nanogpt/prj/ccf-conference/full_program_results.json', 'w') as f:
    json.dump({k: {'total': len(v), 'cn': sum(1 for p in v if p['cn']),
                   'pct': round(sum(1 for p in v if p['cn'])/max(len(v),1)*100,1),
                   'papers': v}
               for k, v in all_results.items()}, f, ensure_ascii=False, indent=2)
print('\nSaved to full_program_results.json')
