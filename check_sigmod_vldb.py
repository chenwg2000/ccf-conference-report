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
    for i in range(1, len(lines)):
        line = lines[i]
        if '(' not in line or ')' not in line: continue
        prev = lines[i-1]
        if '(' in prev or len(prev) < 10: continue
        insts = [x for x in re.findall(r'\(([^)]{4,90})\)', line)
                 if not any(b in x.lower() for b in BAD)]
        if not insts: continue
        papers.append({'t': prev[:60], 'affil': insts[0], 'cn': is_cn(insts[0])})
    return papers

with sync_playwright() as pw:
    browser = pw.chromium.launch(headless=True)
    page = browser.new_page()
    page.set_extra_http_headers({'User-Agent': 'Mozilla/5.0 Chrome/120.0.0.0'})

    # SIGMOD: full scroll
    page.goto('https://2025.sigmod.org/sigmod_papers.shtml', timeout=45000, wait_until='domcontentloaded')
    time.sleep(4)
    for _ in range(40):
        page.evaluate('window.scrollTo(0, document.body.scrollHeight)')
        time.sleep(1.2)
    text = page.inner_text('body')
    lines = [l.strip() for l in text.split('\n') if l.strip()]
    papers = parse(text)
    cn = sum(1 for p in papers if p['cn'])
    print(f'SIGMOD main (40 scrolls): {len(papers)} papers, {cn} CN ({cn/max(len(papers),1)*100:.1f}%)')
    print(f'Total lines: {len(lines)}')
    # Check for pagination links in HTML
    html = page.content()
    for link_pattern in [r'page=\d+', r'offset=\d+', r'start=\d+', r'>Next<', r'next-page']:
        found = re.findall(link_pattern, html)[:3]
        if found:
            print(f'  Pagination hint ({link_pattern}): {found}')

    # VLDB: try DBLP HTML page directly
    print('\n--- VLDB via DBLP HTML ---')
    vldb_urls = [
        'https://vldb.org/2025/',
        'https://dblp.org/db/journals/pvldb/pvldb18.html',
    ]
    for url in vldb_urls:
        try:
            page.goto(url, timeout=35000, wait_until='domcontentloaded')
            time.sleep(3)
            # Scroll a bit
            for _ in range(5):
                page.evaluate('window.scrollTo(0, document.body.scrollHeight)')
                time.sleep(1)
            text = page.inner_text('body')
            lines2 = [l.strip() for l in text.split('\n') if l.strip()]
            p2 = parse(text)
            cn2 = sum(1 for pp in p2 if pp['cn'])
            print(f'  {url[-50:]} -> {len(p2)} parsed, {cn2} CN, {len(lines2)} lines')
            # Show first few entries
            for pp in p2[:2]:
                mark = "CN" if pp['cn'] else "  "
                print(f'    [{mark}] affil={pp["affil"][:50]}')
        except Exception as e:
            print(f'  {url[-50:]} -> ERROR: {str(e)[:50]}')

    # Try ISCA with longer wait (JS-heavy page)
    print('\n--- ISCA 2025 ---')
    isca_urls = [
        'https://iscaconf.org/isca2025/program.php',
        'https://iscaconf.org/isca2025/accepted-papers.php',
    ]
    for url in isca_urls:
        try:
            page.goto(url, timeout=45000, wait_until='networkidle')
            time.sleep(6)
            text = page.inner_text('body')
            lines3 = [l.strip() for l in text.split('\n') if l.strip()]
            p3 = parse(text)
            cn3 = sum(1 for pp in p3 if pp['cn'])
            print(f'  {url[-50:]} -> {len(p3)} parsed, {cn3} CN, {len(lines3)} lines')
            if lines3:
                for l in lines3[5:10]:
                    print(f'    {repr(l[:80])}')
        except Exception as e:
            print(f'  {url[-50:]} -> ERROR: {str(e)[:50]}')

    browser.close()
