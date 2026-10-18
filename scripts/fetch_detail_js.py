"""抓取详情页与播放器相关 JS，落盘供分析。"""

import os
import re

import requests

UA = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/131.0.0.0 Safari/537.36"}
BASE = "https://91porna.com"
TMP = os.environ.get("TEMP", r"C:\Users\79017\AppData\Local\Temp")

s = requests.Session()
s.headers.update(UA)

r = s.get(BASE + "/comic/index/detail?video_key=412915", timeout=25)
html = r.text
open(os.path.join(TMP, "91_detail.html"), "w", encoding="utf-8", errors="ignore").write(html)
print("detail page:", len(html), "bytes")

scripts = re.findall(r'<script[^>]*src="([^"]+)"', html)
for src in scripts:
    if "googletagmanager" in src or "cdn-cgi" in src:
        continue
    url = src if src.startswith("http") else BASE + src
    name = re.sub(r"[^\w.-]", "_", src.split("?")[0].replace("/static/web/js/", ""))
    try:
        rs = s.get(url, timeout=25)
        path = os.path.join(TMP, "91_js_" + name.replace("/", "_"))
        open(path, "wb").write(rs.content)
        print(f"{src} -> {len(rs.content)} bytes -> {path}")
    except Exception as e:
        print(f"{src} FAIL {e}")

# 页面内联 script 中找可疑数据（长 base64 / hex / 自定义密文标记）
print("\n==== 内联 script 数据线索 ====")
for i, m in enumerate(re.finditer(r"<script(?![^>]*src)[^>]*>(.*?)</script>", html, re.S)):
    body = m.group(1)
    if len(body) < 50:
        continue
    hits = []
    for pat, tag in [(r"['\"]([A-Za-z0-9+/=]{200,})['\"]", "long-base64"),
                     (r"['\"]([0-9a-fA-F]{200,})['\"]", "long-hex"),
                     (r"(videourl|video_url|playurl|source|url)\s*[:=]", "url-ish"),
                     (r"(eval\(|atob\(|fromCharCode|String\.fromCharCode)", "eval-ish")]:
        found = re.findall(pat, body)
        if found:
            hits.append(f"{tag}x{len(found)}")
    if hits:
        print(f"inline script #{i}: len={len(body)} hits={hits}")
        open(os.path.join(TMP, f"91_inline_{i}.js"), "w", encoding="utf-8", errors="ignore").write(body)
        print(f"  -> saved {TMP}\\91_inline_{i}.js  head: {body[:200]!r}")
