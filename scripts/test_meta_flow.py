"""端到端验证：手动提交 -> source=manual + 封面文件 + tags 入库"""

import glob
import json
import os
import time

import requests

API = "http://127.0.0.1:8765/api"
time.sleep(4)

# 用一个还没提交过的 melonshort 视频验证
url = "https://91porna.com/melonshort/video/33858"
r = requests.post(API + "/manual/submit", timeout=15,
                  json={"detail_url": url, "title": None})
print("submit:", r.json())

deadline = time.time() + 120
while time.time() < deadline:
    v = requests.get(API + "/manual/state", params={"detail_url": url}, timeout=10).json()["video"]
    if v and v["status"] in ("done", "failed"):
        break
    time.sleep(4)

print("video:", json.dumps(v, ensure_ascii=False)[:400])

# 封面文件
covers = glob.glob(r"D:\python\video_spider\data\covers\*")
print("\n封面文件:", [(os.path.basename(f), "%.1f KB" % (os.path.getsize(f) / 1024)) for f in covers])

# 存量批量视频的 source 默认值
batch = requests.get(API + "/videos", params={"category_id": 5, "limit": 1}, timeout=10).json()["videos"]
print("存量批量视频 source:", batch[0]["source"] if batch else "无")
