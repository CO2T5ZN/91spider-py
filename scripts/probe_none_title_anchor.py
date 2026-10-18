"""同一次请求内：解析列表 -> 找 None 标题条目 -> 查看其锚点结构"""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from lxml import etree  # noqa: E402

from app import db  # noqa: E402
from app.scraper import parser  # noqa: E402
from app.scraper.client import SiteClient  # noqa: E402

db.init()
client = SiteClient()
path = "/comic/index/search?keyword=%E8%90%9D%E8%8E%89"
html = client.get_text(parser.page_url(path, 1))
tree = etree.HTML(html)
items = parser.parse_list_items(html, "search", path)
none_items = [it for it in items if not it["title"]]
print(f"条目 {len(items)} 个，None 标题 {len(none_items)} 个")
if not none_items:
    sys.exit(0)

key = none_items[0]["video_key"]
print("样本 video_key:", key)
anchors = tree.xpath(f'//a[contains(@href, "video_key={key}")]')
print(f"该 key 的锚点数: {len(anchors)}")
for a in anchors:
    outer = etree.tostring(a, encoding="unicode")
    print("--- anchor ---")
    print(outer.replace("\n", " ")[:1000])
    print("texts:", [t.strip() for t in a.xpath(".//text()") if t.strip()])
    print("img alt:", a.xpath(".//img/@alt"))
    print()
