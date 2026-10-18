import os
import re
import urllib.parse
from collections import Counter

tmp = os.environ.get("TEMP", r"C:\Users\79017\AppData\Local\Temp")
html = open(os.path.join(tmp, "91porna_home.html"), encoding="utf-8", errors="ignore").read()
print("html length:", len(html))

links = re.findall(r'href="([^"]+)"', html)
paths = Counter()
for l in links:
    p = urllib.parse.urlparse(l).path
    paths[p] += 1
print("== all link paths ==")
for p, c in sorted(paths.items()):
    print(f"{c:5d}  {p}")

# 找导航/分类相关关键词
print("\n== nav-like segments ==")
for m in re.finditer(r'<a[^>]+href="([^"]*)"[^>]*>(.*?)</a>', html, re.S):
    href, text = m.group(1), re.sub(r"<[^>]+>", "", m.group(2)).strip()
    if text and len(text) <= 30:
        print(f"{text!r:40s} -> {href}")
