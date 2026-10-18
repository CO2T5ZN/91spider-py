"""探测其他类型详情页的 m3u8 解析兼容性"""

import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app import db  # noqa: E402
from app.scraper import parser  # noqa: E402
from app.scraper.client import SiteClient  # noqa: E402

db.init()
client = SiteClient()

samples = {
    "av": "https://91porna.com/comic/index/avdetail?video_key=",
    "melonshort": "https://91porna.com/melonshort/video/",
    "heiliao": "https://91porna.com/heiliao-chigua/",
}

# 从各类型列表页抓一个真实 key
lists = {
    "av": "/comic/av/relvideo?model=107&type=tag&order=week",
    "melonshort": "/melonshort/cat/amateur",
    "heiliao": "/%E9%BB%91%E6%96%99%E5%90%83%E7%93%9C/%E4%BB%8A%E6%97%A5%E5%90%83%E7%93%9C/%E6%9C%80%E6%96%B0",
}
keys = {}
for ctype, path in lists.items():
    html = client.get_text(parser.page_url(path, 1))
    items = parser.parse_list_items(html, ctype, path)
    keys[ctype] = items[0] if items else None
    print(f"{ctype}: {len(items)} items, first={items[0] if items else None}")

for ctype, item in keys.items():
    if not item:
        continue
    html = client.get_text(item["detail_url"])
    tokens = re.findall(r"[0-9a-f]{100,}", html)
    has_video_id = "videoId" in html or "video_id" in html
    direct = re.search(r'https?://[^"\'\s\\|]+\.m3u8\?[^"\'\s\\|]*', html)
    print(f"\n== {ctype} {item['detail_url'][:70]}")
    print(f"   len={len(html)} videoId={has_video_id} hex_tokens={[len(t) for t in tokens[:3]]} direct_m3u8={bool(direct)}")
    url = parser.extract_m3u8_url(html, item["detail_url"], client)
    print(f"   extract_m3u8_url -> {(url or 'None')[:130]}")
