"""定位脏标题数据：分布、来源分类、样本"""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app import db  # noqa: E402

db.init()

# 脏标题模式：top-N、纯数字、超短
rows = db.query_all(
    "SELECT id, title, detail_url, category_id, status FROM videos "
    "WHERE title IS NULL OR TRIM(title) = '' OR LENGTH(TRIM(title)) <= 6 "
    "OR title GLOB 'top-[0-9]*' OR title GLOB '[0-9]*' OR title GLOB '[0-9]:[0-9]*' "
    "ORDER BY id LIMIT 60")
print("可疑标题记录数（前60）:", len(rows))
from collections import Counter
c = Counter()
for r in rows:
    print(f"id={r['id']} cat={r['category_id']} status={r['status']} title={r['title']!r} url={r['detail_url'][:70]}")
    c[r["category_id"]] += 1
print("\n按分类分布:", dict(c))

# 各分类名称
cats = {x["id"]: x["name"] for x in db.list_categories()}
for k, v in c.items():
    print(f"cat {k} = {cats.get(k)}")
