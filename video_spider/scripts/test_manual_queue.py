"""插件队列端到端测试：提交→单线程串行→去重→完成"""

import json
import time

import requests

API = "http://127.0.0.1:8765/api"


def submit(url, title=None):
    r = requests.post(API + "/manual/submit", timeout=15,
                      json={"detail_url": url, "title": title})
    return r.status_code, r.json()


def state(url):
    r = requests.get(API + "/manual/state", params={"detail_url": url}, timeout=15)
    return r.json()


# 1) 非法 URL
code, body = submit("https://91porna.com/moviesets")
print("1) 非法URL:", code, body.get("detail", "")[:40])

# 2) 提交 3 个真实视频（melonshort 2 个短 + heiliao 1 个）
urls = [
    "https://91porna.com/melonshort/video/33862",
    "https://91porna.com/melonshort/video/33863",
    "https://91porna.com/heiliao-chigua/18917711096",
]
for i, u in enumerate(urls):
    code, body = submit(u, f"插件测试视频{i + 1}")
    print(f"2) 提交#{i + 1}:", code, body)

# 3) 重复提交第 1 个
code, body = submit(urls[0])
print("3) 重复提交:", code, body)

# 4) 轮询观察单线程性：downloading_count 永远 <= 1
print("4) 观察队列执行（40s）...")
max_dl = 0
seen_downloading = []
deadline = time.time() + 40
while time.time() < deadline:
    s = state(urls[0])
    max_dl = max(max_dl, s["downloading_count"])
    done = sum(1 for u in urls if (state(u)["video"] or {}).get("status") == "done")
    seen_downloading.append((s["downloading_count"], s["queue_count"]))
    print(f"   t={int(40 - (deadline - time.time())):2d}s downloading={s['downloading_count']} "
          f"queue={s['queue_count']} done={done}")
    if done == 3:
        break
    time.sleep(4)
print("4) downloading_count 最大值:", max_dl, "（单线程要求 <=1）")

# 5) 最终状态
for u in urls:
    s = state(u)
    v = s["video"]
    print("5)", u.split("/")[-1], v["status"] if v else None,
          f"{v['done_segments']}/{v['total_segments']}" if v else "")

# 6) 插件任务禁止改线程数
tasks = requests.get(API + "/tasks", timeout=10).json()["tasks"]
manual_task = next((t for t in tasks if t["category_id"] == state(urls[0])["video"]["id"] // 1 or True), None)
# 找 manual 任务：按分类名找
cats = requests.get(API + "/categories", timeout=10).json()["categories"]
manual_cat = next((c for c in cats if c["type"] == "manual"), None)
mt = next((t for t in tasks if t["category_id"] == manual_cat["id"]), None) if manual_cat else None
if mt:
    r = requests.patch(f"{API}/tasks/{mt['id']}", json={"thread_count": 4}, timeout=10)
    print("6) 改插件任务线程数:", r.status_code, r.json().get("detail", "")[:40])
else:
    print("6) 未找到插件任务")
