import os
import re
import sys

TMP = os.environ.get("TEMP", r"C:\Users\79017\AppData\Local\Temp")


def load(name):
    return open(os.path.join(TMP, f"91_{name}.html"), encoding="utf-8", errors="ignore").read()


html = load("video_play")
# 找 page=2 上下文
for m in re.finditer(r"page=2", html):
    s = max(0, m.start() - 1500)
    seg = html[s:m.end() + 500]
    print("=== context around page=2 ===")
    print(seg)
    print()
    break
