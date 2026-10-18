import os
import re

TMP = os.environ.get("TEMP", r"C:\Users\79017\AppData\Local\Temp")


def load(name):
    return open(os.path.join(TMP, f"91_{name}.html"), encoding="utf-8", errors="ignore").read()


html = load("video_play")
print("===== context of category=play & other cats =====")
for cat in ["play", "new_update", "hd", "ten_minutes"]:
    for m in re.finditer(r'category=' + cat + r'"', html):
        seg = html[m.start() - 250:m.start() + 300]
        print(f"\n--- {cat} ---")
        print(re.sub(r"\s+", " ", seg))
        break  # 第一个出现即可

# title 里可能有分类名
t = re.search(r"<title>([^<]*)</title>", html)
print("\ntitle:", t.group(1))

html3 = load("melonshort")
print("\n===== melonshort: ajax/api hints =====")
for pat in [r'window\.__[A-Z_]+__', r'/api/[^"\']+', r'axios|fetch\(', r'__NUXT__|__INITIAL_STATE__']:
    hits = re.findall(pat, html3)
    print(pat, "->", len(hits), hits[:5])
# melonshort 页面上 直接数 video 条目
vids = re.findall(r'/melonshort/video/(\d+)', html3)
print("video items on page:", len(set(vids)))
# 标题
t = re.search(r"<title>([^<]*)</title>", html3)
print("title:", t.group(1))
