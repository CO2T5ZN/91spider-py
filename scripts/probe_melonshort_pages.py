"""melonshort 分类翻页模式探测"""

import re

import requests

UA = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/131.0.0.0 Safari/537.36"}
s = requests.Session()
s.headers.update(UA)

for u in ["/melonshort/cat/amateur?page=2", "/melonshort/cat/amateur/2", "/melonshort/cat/amateur/p2"]:
    r = s.get("https://91porna.com" + u, timeout=25)
    t = r.text
    ms = len(set(re.findall(r"/melonshort/video/\d+", t)))
    pager = re.search(r'<ul class="pager[^"]*"[^>]*>', t)
    attrs = dict(re.findall(r'data-([\w-]+)="([^"]*)"', pager.group(0))) if pager else None
    nxt = re.findall(r'href="([^"]*(?:page|/p/)[^"]*)"', t)[:6]
    print(u, r.status_code, "items=", ms, "pager=", attrs, "next=", nxt)
