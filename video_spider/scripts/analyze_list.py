import os
import re
import sys
import urllib.parse

TMP = os.environ.get("TEMP", r"C:\Users\79017\AppData\Local\Temp")


def load(name):
    return open(os.path.join(TMP, f"91_{name}.html"), encoding="utf-8", errors="ignore").read()


def analyze(name, html):
    print(f"\n{'='*70}\n[{name}]  length={len(html)}")
    # 1) 分页相关链接
    hrefs = re.findall(r'href="([^"]*(?:page|p[/=])[^"]*)"', html, re.I)
    uniq = []
    for h in hrefs:
        if h not in uniq:
            uniq.append(h)
    print("-- pagination-like hrefs (uniq, first 30):")
    for h in uniq[:30]:
        print("   ", h)
    # 2) 分页容器文本
    for pat in [r'class="[^"]*pag[^"]*"[^>]*>(.{0,400}?)</[a-z]+>\s*</',
                r'<ul[^>]*class="[^"]*page[^"]*"[^>]*>(.*?)</ul>',
                r'class="[^"]*next[^"]*"']:
        for m in re.findall(pat, html, re.S | re.I)[:3]:
            print(f"-- pag container ({pat[:20]}):", re.sub(r"\s+", " ", m)[:400])
    # 3) 视频条目统计: detail 链接数量
    det = len(set(re.findall(r'href="(/comic/index/detail\?video_key=\d+)"', html)))
    avdet = len(set(re.findall(r'href="(/comic/index/avdetail\?video_key=[^"]+)"', html)))
    print(f"-- unique detail links: detail={det}, avdetail={avdet}")
    # 4) 总数/页数文本
    for m in re.findall(r">[^<]*(?:共|总数|页数|条)[^<]*<", html)[:10]:
        print("-- count text:", m)
    # 5) video_key 数组(js内)
    keys = re.findall(r"video_key[\"']?\s*[:=]\s*[\"']?(\w+)", html)
    print("-- video_key occurrences:", len(keys), "uniq:", len(set(keys)))


for n in sys.argv[1:]:
    analyze(n, load(n))
