"""查看排行榜锚点完整结构，确认真实标题位置"""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from lxml import etree  # noqa: E402

from app import db  # noqa: E402
from app.scraper import parser  # noqa: E402
from app.scraper.client import SiteClient  # noqa: E402

db.init()
client = SiteClient()
html = client.get_text(parser.page_url("/comic/index/search?keyword=%E8%90%9D%E8%8E%89", 1))
tree = etree.HTML(html)

for a in tree.xpath('//a[contains(@href, "video_key=356705")]'):
    outer = etree.tostring(a, encoding="unicode")
    print("--- anchor (完整) ---")
    print(outer.replace("\n", " ")[:1200])
    print("texts:", [t.strip() for t in a.xpath(".//text()") if t.strip()])
    print("img alt:", a.xpath(".//img/@alt"))
    print()

# 该锚点周围（父级容器）有没有相邻的标题文本
for a in tree.xpath('//a[contains(@href, "video_key=356705")]')[:1]:
    parent = a.getparent()
    seg = etree.tostring(parent, encoding="unicode")
    print("--- 父容器 (前 1500 字) ---")
    print(seg.replace("\n", " ")[:1500])
