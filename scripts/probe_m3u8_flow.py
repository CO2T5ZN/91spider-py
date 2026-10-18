"""验证 m3u8 链路：参数容错性、播放列表结构、分片可下载性"""

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
u = re.findall(r"[0-9a-f]{150,}", html)[0]
img = "%2Fupload_01%2Fxiao%2F20260914%2F2026091416340088133.jpeg"
t = int(time.time() // 2100)


def play_url(img_=img, u_=u, h_="", t_=t):
    return f"{BASE}/index/detail_play?img={img_}&ads=&u={u_}&h={h_}&t={t_}"


print("==== 参数容错性 ====")
for name, url in [
    ("完整参数", play_url()),
    ("img为空", play_url(img_="")),
    ("t=0", play_url(t_=0)),
    ("无Referer", None),
]:
    if url is None:
        s2 = requests.Session()
        s2.headers.update({"User-Agent": UA["User-Agent"]})
        resp = s2.get(play_url(), timeout=25)
    else:
        resp = s.get(url, timeout=25)
    m3 = re.search(r"https?://[^'\"]+\.m3u8\?[^'\"]*", resp.text)
    print(f"{name}: HTTP {resp.status_code} len={len(resp.text)} m3u8={'有' if m3 else '无'}")

print("\n==== m3u8 内容 ====")
m3u8_url = m3.group(0)
print("URL:", m3u8_url[:150])
rm = s.get(m3u8_url, timeout=25, headers={"Referer": "https://91porna.com/"})
print(f"HTTP {rm.status_code}, {len(rm.text)} bytes")
print(rm.text[:800])

print("\n==== 第一个分片下载测试 ====")
lines = [ln.strip() for ln in rm.text.splitlines()]
seg = next((ln for ln in lines if ln and not ln.startswith("#")), None)
if seg:
    from urllib.parse import urljoin
    seg_url = urljoin(m3u8_url, seg)
    print("segment:", seg_url[:120])
    rs = s.get(seg_url, timeout=30)
    print(f"HTTP {rs.status_code}, {len(rs.content)} bytes, head={rs.content[:4].hex()}")
