import os
import re

TMP = os.environ.get("TEMP", r"C:\Users\79017\AppData\Local\Temp")


def load(name):
    return open(os.path.join(TMP, f"91_{name}.html"), encoding="utf-8", errors="ignore").read()


# 1) video 页: 分类切换器(可能是 select 或 a 标签)
html = load("video_play")
print("===== video_play category switcher =====")
for m in re.finditer(r'<select[^>]*>(.*?)</select>', html, re.S):
    opts = re.findall(r'<option[^>]*value="([^"]*)"[^>]*>([^<]*)</option>', m.group(1))
    if opts:
        print("select:", opts[:60])
# 所有 category= 出现
cats = {}
for m in re.finditer(r'category=(\w+)', html):
    cats[m.group(1)] = cats.get(m.group(1), 0) + 1
print("category= occurrences:", cats)

# 2) av_index 页: model/theme/tag 列表
html2 = load("av_index")
print("\n===== av_index models =====")
rels = re.findall(r'href="(/comic/av/relvideo\?model=(\d+)&amp;type=(\w+)[^"]*)"[^>]*>\s*([^<>]{1,40}?)\s*</a>', html2)
seen = {}
for href, mid, typ, label in rels:
    key = (mid, typ)
    if key not in seen and label.strip():
        seen[key] = label.strip()
themes = {k: v for k, v in seen.items() if k[1] == 'theme'}
tags = {k: v for k, v in seen.items() if k[1] == 'tag'}
print(f"themes ({len(themes)}):", themes)
print(f"tags ({len(tags)}):", tags)

# av_index 自己的分页
for m in re.finditer(r'<ul class="pager[^"]*"[^>]*>', html2):
    print("av_index pager:", dict(re.findall(r'data-([\w-]+)="([^"]*)"', m.group(0))))

# 3) melonshort 分页结构
html3 = load("melonshort")
print("\n===== melonshort pagination =====")
for m in re.finditer(r'class="[^"]*pager[^"]*"[^>]*>', html3):
    print("pager-ish:", m.group(0)[:300])
pags = re.findall(r'href="([^"]*melonshort[^"]*(?:page|/p/|\?p=)[^"]*)"', html3)
print("page links:", list(dict.fromkeys(pags))[:20])
# 看 melonshort 页面里所有 a 的 href 去重(找翻页模式)
hrefs = re.findall(r'href="([^"]+)"', html3)
ms = [h for h in hrefs if 'melonshort' in h]
print("melonshort hrefs uniq:", sorted(set(ms))[:40])
