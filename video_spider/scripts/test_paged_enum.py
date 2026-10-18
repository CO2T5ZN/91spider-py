"""验证按页加载：任务创建后 videos.total 应逐页增长（而非一次预读全部）"""

import time

import requests

API = "http://127.0.0.1:8765/api"
time.sleep(4)

# 找一个还没有任务的分类（成人动漫，147 个）
cats = requests.get(API + "/categories", timeout=10).json()["categories"]
tasks = requests.get(API + "/tasks", timeout=10).json()["tasks"]
used = {t["category_id"] for t in tasks}
cat = next(c for c in cats if c["id"] == 38 and c["name"] == "成人动漫")
assert cat["id"] not in used, "该分类已有任务"

r = requests.post(API + "/tasks", timeout=15,
                  json={"category_id": cat["id"], "thread_count": 4})
print("create:", r.status_code, r.json().get("task", {}).get("progress") or r.json().get("detail"))

# 观察 60 秒：total 应从 0 -> ~34（第1页）-> 等待下载 -> 之后才出现 ~68
print("t=0s   total=0 (刚创建)")
for sec in range(5, 65, 5):
    p = requests.get(API + "/videos", params={"category_id": cat["id"], "limit": 1}, timeout=10).json()["summary"]
    print(f"t={sec:2d}s  total={p['total']:4d} done={p['done']:3d} downloading={p['downloading']} pending={p['pending']:4d}")
    time.sleep(5)

# 暂停，避免继续大量下载
t = requests.get(API + "/tasks", timeout=10).json()["tasks"][0]
requests.post(f"{API}/tasks/{t['id']}/pause", timeout=10)
print("已暂停任务", t["id"], "（验证分页行为即可，不实际全量下载）")
