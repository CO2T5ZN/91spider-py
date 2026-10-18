"""重新提交失败的视频，验证修复后能下载成功"""

import time

import requests

API = "http://127.0.0.1:8765/api"
urls = [
    "https://91porna.com/melonshort/video/33862",
    "https://91porna.com/melonshort/video/33863",
]

for u in urls:
    r = requests.post(API + "/manual/submit", timeout=15, json={"detail_url": u, "title": None})
    print("resubmit:", r.json())

deadline = time.time() + 90
while time.time() < deadline:
    states = []
    for u in urls:
        v = requests.get(API + "/manual/state", params={"detail_url": u}, timeout=10).json()["video"]
        states.append(v["status"] if v else "?")
    print(time.strftime("%H:%M:%S"), states)
    if all(s == "done" for s in states):
        print("全部完成")
        break
    if all(s in ("done", "failed") for s in states):
        print("已终态")
        break
    time.sleep(5)
