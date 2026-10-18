"""验证 video 事件字段完整性（基于现存任务）"""

import json
import time

import requests

API = "http://127.0.0.1:8765/api"

tasks = requests.get(API + "/tasks", timeout=10).json()["tasks"]
print("tasks:", [(t["id"], t["category_id"], t["state"], t["progress"]) for t in tasks])
tid = tasks[0]["id"]

r = requests.post(f"{API}/tasks/{tid}/start", timeout=10)
print("start:", r.status_code, r.text[:120])

resp = requests.get(API + "/events", stream=True, timeout=30)
rows, buf, deadline = [], [], time.time() + 20
for line in resp.iter_lines(decode_unicode=True):
    if time.time() > deadline or len(rows) >= 40:
        break
    if line and line.startswith("data: "):
        buf.append(line[6:])
    elif line == "" and buf:
        try:
            d = json.loads("".join(buf))
        except Exception:
            d = None
        buf = []
        if isinstance(d, dict):
            rows.append(d)
resp.close()

kinds = {}
for d in rows:
    kinds[d.get("event", "?")] = kinds.get(d.get("event", "?"), 0) + 1
print("事件分布:", kinds)
vids = [d for d in rows if "video_key" in d]
print("video 事件数:", len(vids))
for v in vids[:8]:
    print(f"id={v['id']} key={v['video_key']} title={(v['title'] or '')[:18]!r} "
          f"status={v['status']} segs={v['done_segments']}/{v['total_segments']}")
print("空 key/title 的 video 事件:", len([v for v in vids if not v["video_key"] or not v["title"]]))
