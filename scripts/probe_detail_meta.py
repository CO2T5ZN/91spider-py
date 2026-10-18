"""探查详情页的标签和封面结构"""

import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from lxml import etree  # noqa: E402

from app import db  # noqa: E402
from app.scraper import parser  # noqa: E402
from app.scraper.client import SiteClient  # noqa: E402

db.init()

client = SiteClient()
url = "https://91porna.com/comic/index/detail?video_key=412915"
html = client.get_text(url)
tree = etree.HTML(html)

# meta 标签
print("=== meta ===")
for m in tree.xpath("//meta"):
    key = m.get("property") or m.get("name")
    if key and m.get("content"):
        print(f"  {key}: {m.get('content')[:100]}")

# og:image / 封面
print("\nog:image:", tree.xpath('//meta[@property="og:image"]/@content'))

# 可能的标签元素：class 含 tag / label / keyword / category
print("\n=== tag-ish 元素 ===")
for el in tree.xpath('//*[contains(@class,"tag") or contains(@class,"label") or contains(@class,"keyword") or contains(@class,"cate")]')[:15]:
    text = "".join(el.xpath(".//text()")).strip()[:40]
    href = el.get("href", "")[:60] if el.tag == "a" else ""
    print(f"  <{el.tag} class={el.get('class','')[:50]!r}> text={text!r} href={href!r}")

# 详情页通常有分类/标签链接指向 search 页
print("\n=== 指向 search 的链接（标签） ===")
for a in tree.xpath('//a[contains(@href,"/comic/index/search?keyword=")]')[:20]:
    text = "".join(a.xpath(".//text()")).strip()
    cls = a.get("class", "")[:60]
    print(f"  {text!r:24s} class={cls!r} href={a.get('href', '')[:70]}")

# 视频信息区（时长/作者等）
print("\n=== video-info 类元素 ===")
for el in tree.xpath('//*[contains(@class,"video-info") or contains(@class,"detail-info") or contains(@class,"info-item")]')[:10]:
    text = " ".join(t.strip() for t in el.xpath(".//text()") if t.strip())[:80]
    print(f"  <{el.tag} class={el.get('class','')[:50]!r}> {text!r}")
