import os
import re
import requests

UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36"
TMP = os.environ.get("TEMP", r"C:\Users\79017\AppData\Local\Temp")
BASE = "https://91porna.com"

pages = {
    "video_play": "/comic/index/video?category=play",
    "video_original": "/comic/index/video?category=original",
    "av_relvideo": "/comic/av/relvideo?model=1&type=theme&order=week",
    "av_index": "/comic/index/av",
    "melonshort": "/melonshort",
    "heiliao": "/%E9%BB%91%E6%96%99%E5%90%83%E7%93%9C/%E6%8E%A8%E8%8D%90",
    "moviesets": "/moviesets",
}

s = requests.Session()
s.headers.update({"User-Agent": UA})

for name, path in pages.items():
    try:
        r = s.get(BASE + path, timeout=20)
        fn = os.path.join(TMP, f"91_{name}.html")
        open(fn, "w", encoding="utf-8", errors="ignore").write(r.text)
        print(f"{name}: HTTP {r.status_code}, {len(r.text)} bytes -> {fn}")
    except Exception as e:
        print(f"{name}: FAILED {e}")
