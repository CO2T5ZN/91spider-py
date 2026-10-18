"""清理 videos.title 脏数据：
1. 垃圾标题（top-N / 名次数字 / 时长）置为 NULL
2. 已完成视频若标题为空，从详情页回填真实标题（数量有限）
"""

import sys

sys.path.insert(0, r"D:\python\video_spider")

from app import db
from app.scraper import parser
from app.scraper.client import SiteClient

db.init()

# 1) 找出所有垃圾标题
rows = db.query_all("SELECT id, title, status, detail_url FROM videos WHERE title IS NOT NULL")
dirty = [r for r in rows if not parser.is_clean_title(r["title"])]
print(f"总视频 {len(rows)} 条，其中垃圾标题 {len(dirty)} 条")
from collections import Counter
print("垃圾标题样本:", dict(Counter(r["title"] for r in dirty).most_common(10)))

# 2) 置空
if dirty:
    ids = [r["id"] for r in dirty]
    db.execute("UPDATE videos SET title=NULL, updated_at=? WHERE id IN (%s)"
               % ",".join("?" * len(ids)), tuple([db.now()] + ids))
    print("已置空", len(ids), "条")

# 3) 已完成但标题为空的，从详情页回填
backfill = db.query_all(
    "SELECT id, detail_url FROM videos WHERE status='done' AND title IS NULL")
print(f"已完成且标题为空：{len(backfill)} 条")
if backfill:
    client = SiteClient()
    ok = 0
    for r in backfill[:80]:
        try:
            html = client.get_text(r["detail_url"])
            title = parser.extract_detail_title(html)
            if title:
                db.update_video(r["id"], title=title)
                ok += 1
        except Exception as e:  # noqa: BLE001
            print("  回填失败", r["id"], e)
    client.close()
    print(f"回填成功 {ok}/{len(backfill[:80])}")

# 4) 复查
remaining = [r["title"] for r in db.query_all("SELECT DISTINCT title FROM videos WHERE title IS NOT NULL")
             if not parser.is_clean_title(r["title"])]
nulls = db.query_one("SELECT COUNT(*) AS n FROM videos WHERE title IS NULL")["n"]
print("剩余垃圾标题:", len(remaining), remaining[:5])
print("标题为空（等待下载时自愈）:", nulls, "条")
