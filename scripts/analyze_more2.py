import os
import re
import urllib.parse

TMP = os.environ.get("TEMP", r"C:\Users\79017\AppData\Local\Temp")


def load(name):
    return open(os.path.join(TMP, f"91_{name}.html"), encoding="utf-8", errors="ignore").read()


# 1) video 页: 每个category值的中文标签上下文
html = load("video_play")
print("===== video category labels =====")
for cat in ["play", "now_month_hot", "original", "now_hot", "new_update", "ten_minutes",
            "twenty_minutes", "now_month_collect", "hd", "month_hot", "now_month_comment", "max_collect"]:
    m = re.search(r'category=' + cat + r'"[^>]*>\s*([^<>]{1,40}?)\s*<', html)
    if not m:
        # 尝试 select option
        m = re.search(r'value="' + cat + r'"[^>]*>([^<]*)<', html)
    print(f"{cat:18s} -> {m.group(1).strip() if m else '???'}")

# 2) av_index relvideo 原始链接
html2 = load("av_index")
print("\n===== av_index raw relvideo hrefs =====")
raw = re.findall(r'href="([^"]*relvideo[^"]*)"', html2)
for h in list(dict.fromkeys(raw))[:50]:
    print("  ", h.replace("&amp;", "&"))
# 提取带文本的
pairs = re.findall(r'<a[^>]+href="([^"]*relvideo[^"]*)"[^>]*>(.*?)</a>', html2, re.S)
seen = {}
for href, inner in pairs:
    label = re.sub(r"<[^>]+>", "", inner).strip()
    if label and href not in seen:
        seen[href.replace("&amp;", "&")] = label
print("\nwith labels:")
for k, v in list(seen.items())[:60]:
    print(f"  {v!r:30s} {k}")

# 3) melonshort pager 关键字
html3 = load("melonshort")
print("\n===== melonshort pager keyword =====")
idx = [m.start() for m in re.finditer(r"pager", html3)]
print("pager occurrences:", len(idx))
for i in idx[:3]:
    print(html3[i - 200:i + 600].replace("\n", " ")[:800])
