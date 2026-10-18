"""melonshort 页面 AJAX 接口线索"""

import re

import requests

UA = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/131.0.0.0 Safari/537.36"}
s = requests.Session()
s.headers.update(UA)
r = s.get("https://91porna.com/melonshort/cat/amateur", timeout=25)
t = r.text

for pat in [r'"(/api/[^"]+)"', r"url:\s*['\"]([^'\"]+)['\"]", r'ajax|axios|fetch\(', r'data-page="[^"]*"',
            r'loadmore|load-more|load_more|infinite', r'window\.__\w+__', r'<script[^>]*src="([^"]+melonshort[^"]*)"']:
    hits = re.findall(pat, t)
    print(f"{pat[:40]:42s} -> {len(hits)}", list(dict.fromkeys(hits))[:8])

# 找 script 块里的接口
for m in re.findall(r"<script(?![^>]*src)[^>]*>(.*?)</script>", t, re.S):
    if "melonshort" in m and len(m) < 5000:
        print("---- script block ----")
        print(m[:1500])
