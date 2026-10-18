"""断点续传验证：抓进行中视频 -> 暂停 -> 查分片 -> 继续 -> 对比进度"""

import time

import requests

API = "http://127.0.0.1:8765/api"


def get(path):
    return requests.get(API + path, timeout=15).json()


def post(path):
    return requests.post(API + path, timeout=15).json()


# 等一个下载中的视频
target = None
for _ in range(30):
    vids = get("/videos?category_id=29&status=downloading&limit=5")["videos"]
    # done_segments 字段不在 REST 返回里，直接看哪个 total_segments 有值
    if vids:
        target = vids[0]
        break
    time.sleep(2)
print("target video:", target["id"], target["video_key"], "total", target["total_segments"])

post("/tasks/1/pause")
time.sleep(1)
import sqlite3
conn = sqlite3.connect(r"D:\python\video_spider\data\spider.db")
conn.row_factory = sqlite3.Row
vid = target["id"]
row = conn.execute("SELECT status, total_segments FROM videos WHERE id=?", (vid,)).fetchone()
done_before = conn.execute("SELECT COUNT(*) AS n FROM segments WHERE video_id=? AND status='done'", (vid,)).fetchone()["n"]
print(f"paused: video status={row['status']} total={row['total_segments']} segs_done={done_before}")

post("/tasks/1/start")
print("resumed, waiting 10s...")
time.sleep(10)
row = conn.execute("SELECT status FROM videos WHERE id=?", (vid,)).fetchone()
segs_now = conn.execute("SELECT COUNT(*) AS n FROM segments WHERE video_id=? AND status='done'", (vid,)).fetchone()["n"]
print(f"after resume: video status={row['status']} segs_done={segs_now} (before={done_before})")
print("RESUME OK" if segs_now >= done_before else "PROBLEM: progress lost")
conn.close()
