"""探查视频详情页的 m3u8 提取方式"""

import re
import requests

UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36"
BASE = "https://91porna.com"
s = requests.Session()
s.headers.update({"User-Agent": UA})

# 先从列表页拿一个真实 detail key
r = s.get(BASE + "/comic/index/video?category=original", timeout=25)
keys = list(dict.fromkeys(re.findall(r'/comic/index/detail\?video_key=(\d+)', r.text)))[:3]
print("sample keys:", keys)

for k in keys:
    url = f"{BASE}/comic/index/detail?video_key={k}"
    r = s.get(url, timeout=25)
    t = r.text
    print(f"\n== {k}: HTTP {r.status_code} len={len(t)} title={re.search(r'<title>([^<]*)</title>', t).group(1) if re.search(r'<title>([^<]*)</title>', t) else ''}")
    for pat in [r'https?://[^"\'\s]+\.m3u8[^"\'\s]*', r'window\.__\w+__', r'videourl|video_url|source\s*[:=]']:
        hits = re.findall(pat, t)
        print(f"  {pat[:30]:32s} -> {len(hits)}", hits[:2])
    # m3u8 上下文
    m = re.search(r'.{200}\.m3u8.{100}', t, re.S)
    if m:
        print("  ctx:", m.group(0).replace("\n", " ")[:400])
