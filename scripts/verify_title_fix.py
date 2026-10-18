"""验证新解析：列表页不再产生垃圾标题"""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app import db  # noqa: E402
from app.scraper import parser  # noqa: E402
from app.scraper.client import SiteClient  # noqa: E402

db.init()
client = SiteClient()

# 检查可爱萝莉所有页的解析输出
bad = []
total = 0
for page in range(1, 6):
    html = client.get_text(parser.page_url("/comic/index/search?keyword=%E8%90%9D%E8%8E%89", page))
    items = parser.parse_list_items(html, "search", "/comic/index/search?keyword=%E8%90%9D%E8%8E%89")
    total += len(items)
    for it in items:
        if not parser.is_clean_title(it["title"]):
            bad.append((page, it["video_key"], it["title"]))
    print(f"page {page}: {len(items)} 条")
    if not items:
        break

print(f"\n共 {total} 条，垃圾标题 {len(bad)} 条", bad[:5])
client.close()
