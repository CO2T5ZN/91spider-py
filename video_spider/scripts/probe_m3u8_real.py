"""验证 m3u8 本体与分片（修正正则后）"""

import re
import time
from urllib.parse import urljoin

import requests

UA = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/131.0.0.0 Safari/537.36"}
s = requests.Session()
s.headers.update(UA)

r = s.get("https://91porna.com/comic/index/detail?video_key=412915", timeout=25)
u = re.findall(r"[0-9a-f]{150,}", r.text)[0]
t = int(time.time() // 2100)
rp = s.get(f"https://91porna.com/index/detail_play?img=&ads=&u={u}&h=&t={t}", timeout=25)
m = re.search(r"https?://[^'\"|]+\.m3u8\?[^'\"|]*", rp.text)
m3u8 = m.group(0)
print("m3u8:", m3u8[:160])

rm = s.get(m3u8, timeout=25)
print(f"HTTP {rm.status_code}, {len(rm.text)} bytes")
print(rm.text[:600])

lines = [ln.strip() for ln in rm.text.splitlines()]
seg = next((ln for ln in lines if ln and not ln.startswith("#")), None)
if seg:
    seg_url = urljoin(m3u8, seg)
    print("segment:", seg_url[:120])
    rs = s.get(seg_url, timeout=30)
    print(f"HTTP {rs.status_code}, {len(rs.content)} bytes, head={rs.content[:4].hex()}")
    # TS 流应以 0x47 开头
    print("valid TS:", rs.content[:1] == b"\x47")
