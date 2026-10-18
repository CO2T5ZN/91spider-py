"""查看 33863 失败详情"""

import requests

r = requests.get("http://127.0.0.1:8765/api/manual/state",
                 params={"detail_url": "https://91porna.com/melonshort/video/33863"}, timeout=10)
v = r.json()["video"]
print(v)
