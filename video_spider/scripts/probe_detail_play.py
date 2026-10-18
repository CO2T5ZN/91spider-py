"""请求 detail_play 动态脚本，看播放数据如何返回"""

import re
import time

import requests

UA = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/131.0.0.0 Safari/537.36",
      "Referer": "https://91porna.com/comic/index/detail?video_key=412915"}
BASE = "https://91porna.com"
s = requests.Session()
s.headers.update(UA)

r = s.get(BASE + "/comic/index/detail?video_key=412915", timeout=25)
html = r.text

# u 令牌：打包脚本里的长 hex
hex_tokens = re.findall(r"[0-9a-f]{160,}", html)
print("hex tokens:", [t[:40] + f"...(len={len(t)})" for t in hex_tokens[:3]])
u = hex_tokens[0] if hex_tokens else ""
# img 路径：找 jpeg 相关片段
img_m = re.search(r'2Fupload_01', html)
print("img tokens present:", bool(img_m))

t = int(time.time() // 2100)
url = f"{BASE}/index/detail_play?img=%2Fupload_01%2Fxiao%2F20260914%2F2026091416340088133.jpeg&ads=&u={u}&h=&t={t}"
print("GET", url[:120], "...")
rp = s.get(url, timeout=25)
body = rp.text
print(f"HTTP {rp.status_code}, {len(body)} bytes")
print("---- body head ----")
print(body[:3000])

# 找 m3u8 / 加密线索
for pat in [r"m3u8", r"atob|eval|decrypt|CryptoJS|AES", r"['\"]([A-Za-z0-9+/=]{100,})['\"]"]:
    hits = re.findall(pat, body)
    print(f"pat {pat[:30]:32s} -> {len(hits)}", hits[:3])
