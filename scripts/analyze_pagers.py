import os
import re

TMP = os.environ.get("TEMP", r"C:\Users\79017\AppData\Local\Temp")


def load(name):
    return open(os.path.join(TMP, f"91_{name}.html"), encoding="utf-8", errors="ignore").read()


for name in ["video_play", "video_original", "av_relvideo", "av_index", "melonshort", "heiliao", "moviesets"]:
    html = load(name)
    print(f"\n===== {name} =====")
    # pager 元数据
    for m in re.finditer(r'<ul class="pager[^"]*"[^>]*>', html):
        tag = m.group(0)
        attrs = dict(re.findall(r'data-([\w-]+)="([^"]*)"', tag))
        print("pager:", attrs)
    # 视频分类导航 (video页面的category切换)
    cats = re.findall(r'href="(/comic/index/video\?category=(\w+)[^"]*)"', html)
    if cats:
        names = re.findall(r'<a[^>]+href="(/comic/index/video\?category=\w+[^"]*)"[^>]*>\s*([^<>]{1,40}?)\s*</a>', html)
        seen = {}
        for href, label in names:
            label = label.strip()
            if href not in seen and label:
                seen[href] = label
        print("video category nav:", seen)
    # relvideo 的 model/type 参数
    rels = re.findall(r'href="(/comic/av/relvideo\?[^"]*)"[^>]*>\s*([^<>]{1,40}?)\s*</a>', html)
    if rels:
        seen = {}
        for href, label in rels:
            label = label.strip()
            if href not in seen and label:
                seen[href] = label
        items = list(seen.items())
        print(f"relvideo links ({len(items)}):", items[:40])
    # melonshort cat
    ms = re.findall(r'href="(/melonshort[^"]*)"[^>]*>\s*([^<>]{1,40}?)\s*</a>', html)
    if ms:
        seen = {}
        for href, label in ms:
            label = label.strip()
            if href not in seen and label:
                seen[href] = label
        print("melonshort links:", seen)
    # 黑料吃瓜
    hl = re.findall(r'href="(/%E9%BB%91%E6%96%99%E5%90%83%E7%93%9C/[^"]*)"[^>]*>\s*([^<>]{1,40}?)\s*</a>', html)
    if hl:
        seen = {}
        for href, label in hl:
            label = label.strip()
            if href not in seen and label:
                seen[href] = label
        print("heiliao links:", seen)
