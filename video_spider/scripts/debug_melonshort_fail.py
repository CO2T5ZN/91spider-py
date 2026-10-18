"""查看插件队列失败视频的错误信息"""

import requests

r = requests.get("http://127.0.0.1:8765/api/manual/state",
                 params={"detail_url": "https://91porna.com/melonshort/video/33862"}, timeout=10)
print(r.json()["video"])

# 直接重新解析一次看看
import sys, os
sys.path.insert(0, r"D:\python\video_spider")
from app import db
from app.scraper import parser
from app.scraper.client import SiteClient

db.init()
client = SiteClient()
url = "https://91porna.com/melonshort/video/33862"
html = client.get_text(url)
print("page len:", len(html))
m3u8_url = parser.extract_m3u8_url(html, url, client)
print("m3u8:", (m3u8_url or "None")[:150])
if m3u8_url:
    try:
        pl = __import__("app.downloader.m3u8", fromlist=["m3u8"]).parse(client.get_text(m3u8_url), m3u8_url)
        while pl.is_master:
            print("master ->", pl.variant_url[:120])
            pl = __import__("app.downloader.m3u8", fromlist=["m3u8"]).parse(client.get_text(pl.variant_url), pl.variant_url)
        print("segments:", len(pl.segments), "key:", pl.key_url)
    except Exception as e:
        print("m3u8 parse error:", type(e).__name__, e)
