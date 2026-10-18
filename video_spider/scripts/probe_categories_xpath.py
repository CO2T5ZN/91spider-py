"""验证分类提取 XPath：//a[contains(concat(" ", normalize-space(@class), " "), " video-sub-item ")]"""

import os
import re
import sys

import requests
from lxml import etree

UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36"
BASE = "https://91porna.com"
TMP = os.environ.get("TEMP", r"C:\Users\79017\AppData\Local\Temp")

XPATH = '//a[contains(concat(" ", normalize-space(@class), " "), " video-sub-item ")]'


def parse(html_text, source):
    tree = etree.HTML(html_text)
    nodes = tree.xpath(XPATH)
    print(f"\n===== {source}: {len(nodes)} 个 video-sub-item =====")
    for a in nodes:
        href = a.get("href", "")
        text = "".join(a.xpath(".//text()")).strip()
        parent_cls = a.getparent().get("class", "") if a.getparent() is not None else ""
        # 找兄弟节点里是否有数量信息
        sibling_txt = " ".join((t.text or "").strip() for t in a.itersiblings())[:60]
        print(f"  text={text!r:30s} href={href!r:55s} parent={parent_cls!r} sib={sibling_txt!r}")
    return nodes


# 1) 缓存页
cached = open(os.path.join(TMP, "91porna_home.html"), encoding="utf-8", errors="ignore").read()
parse(cached, "cached home")

# 2) 重新抓取
s = requests.Session()
s.headers.update({"User-Agent": UA})
r = s.get(BASE + "/", timeout=25)
print(f"\nlive home: HTTP {r.status_code}, {len(r.text)} bytes")
open(os.path.join(TMP, "91porna_home_fresh.html"), "w", encoding="utf-8", errors="ignore").write(r.text)
fresh_nodes = parse(r.text, "live home")

# 3) 每个分类取第一页，看 pager 数据属性（算视频总数用）
if fresh_nodes:
    sample = fresh_nodes[:6]
    for a in sample:
        href = a.get("href", "")
        if not href or href.startswith(("http", "javascript")) and not href.startswith("/"):
            continue
        url = BASE + href if href.startswith("/") else href
        try:
            rp = s.get(url, timeout=25)
            t = rp.text
            pagers = re.findall(r'<ul class="pager[^"]*"[^>]*>', t)
            det = len(set(re.findall(r'/comic/index/detail\?video_key=\d+', t)))
            avd = len(set(re.findall(r'/comic/index/avdetail\?video_key=\w+', t)))
            ms = len(set(re.findall(r'/melonshort/video/\d+', t)))
            print(f"\npager probe {href}: HTTP {rp.status_code} detail={det} av={avd} short={ms}")
            for p in pagers:
                print("   pager:", p)
        except Exception as e:
            print(f"pager probe {href}: FAIL {e}")
