"""分析列表页视频条目的 HTML 结构，定位脏标题来源"""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from lxml import etree  # noqa: E402

from app import db  # noqa: E402
from app.scraper import parser  # noqa: E402
from app.scraper.client import SiteClient  # noqa: E402

db.init()
client = SiteClient()

lists = {
    "video": "/comic/index/video?category=original",
    "search": "/comic/index/search?keyword=%E8%90%9D%E8%8E%89",
    "av": "/comic/av/relvideo?model=107&type=tag&order=week",
    "melonshort": "/melonshort/cat/amateur",
    "heiliao": "/%E9%BB%91%E6%96%99%E5%90%83%E7%93%9C/%E4%BB%8A%E6%97%A5%E5%90%83%E7%93%9C/%E6%9C%80%E6%96%B0",
}

for ctype, path in lists.items():
    html = client.get_text(parser.page_url(path, 1))
    tree = etree.HTML(html)
    marker = {
        "video": "/comic/index/detail?video_key=",
        "search": "/comic/index/detail?video_key=",
        "av": "/comic/index/avdetail?video_key=",
        "melonshort": "/melonshort/video/",
        "heiliao": "/heiliao-chigua/",
    }[ctype]
    anchors = tree.xpath(f'//a[contains(@href, "{marker}")]')
    print(f"\n===== {ctype}：{len(anchors)} 个条目 =====")
    # 打印前 3 个条目的完整外部 HTML（截断）与 _extract_title 的结果
    for a in anchors[:3]:
        outer = etree.tostring(a, encoding="unicode")
        print("--- item html (前 500 字) ---")
        print(outer[:500].replace("\n", " "))
        print("提取 title 属性:", a.get("title"))
        print("提取 img alt:", a.xpath(".//img/@alt"))
        print("所有文本:", [t.strip() for t in a.xpath(".//text()") if t.strip()])
        print("=> _extract_title:", parser._extract_title(a))
        print()
