import os
import re

TMP = os.environ.get("TEMP", r"C:\Users\79017\AppData\Local\Temp")
html = open(os.path.join(TMP, "91_video_play.html"), encoding="utf-8", errors="ignore").read()

# 找 body 中所有 page= 出现位置及类型
positions = [m.start() for m in re.finditer(r"page=", html)]
print("total 'page=' occurrences:", len(positions))
body_start = html.find("<body")
print("body starts at:", body_start)

for i, p in enumerate(positions):
    kind = "head" if p < body_start else "body"
    ctx = html[max(0, p - 120):p + 80].replace("\n", " ")
    print(f"[{i}] {kind} @{p}: ...{ctx[:200]}")
