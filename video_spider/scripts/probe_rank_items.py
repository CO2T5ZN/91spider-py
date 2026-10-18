"""查看排行榜条目锚点的结构"""

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

# 找 video_key=366501（脏标题 top-1）的所有锚点
for a in tree.xpath('//a[contains(@href, "video_key=366501")]'):
    outer = etree.tostring(a, encoding="unicode")
    print("--- anchor ---")
    print(outer[:600].replace("\n", " "))
    print("texts:", [t.strip() for t in a.xpath(".//text()") if t.strip()])
    print("img alt:", a.xpath(".//img/@alt"))
    print()

# 找页面里 top- 文本所在元素
print("=== 页面中含 top- 文本的元素 ===")
for el in tree.xpath('//*[contains(text(), "top-")]')[:5]:
    parent = el.getparent()
    print(el.tag, "class=", el.get("class", "")[:60], "text=", (el.text or "").strip()[:30])
    href = parent.get("href") if parent is not None else None
    print("  parent:", parent.tag if parent is not None else None,
          parent.get("href", "")[:60] if parent is not None else "")
