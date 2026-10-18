"""探查菜单分组结构 + 各类型分类首页的 pager/条目情况"""

import os
import re
import urllib.parse

import requests
from lxml import etree

UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36"
BASE = "https://91porna.com"
TMP = os.environ.get("TEMP", r"C:\Users\79017\AppData\Local\Temp")

html = open(os.path.join(TMP, "91porna_home_fresh.html"), encoding="utf-8", errors="ignore").read()
tree = etree.HTML(html)

print("===== video-sub-menu 分组结构 =====")
for menu in tree.xpath('//div[contains(@class,"video-sub-menu")]'):
    # 找前一个兄弟 / 父级里的组标题
    prev = menu.getprevious()
    title = None
    node = menu
    for _ in range(4):
        node = node.getparent()
        if node is None:
            break
        cand = node.xpath('./*[contains(@class,"title") or self::h2 or self::h3]/text()')
        if cand:
            title = " | ".join(t.strip() for t in cand)
            break
    items = menu.xpath('./a[contains(concat(" ", normalize-space(@class), " "), " video-sub-item ")]')
    print(f"group_title={title!r} items={len(items)} menu_prev={etree.tostring(prev, encoding='unicode')[:120] if prev is not None else None}")

s = requests.Session()
s.headers.update({"User-Agent": UA})


def probe(path):
    url = BASE + urllib.parse.quote(path, safe="/?=&%")
    r = s.get(url, timeout=25)
    t = r.text
    pager = re.search(r'<ul class="pager[^"]*"[^>]*>', t)
    attrs = dict(re.findall(r'data-([\w-]+)="([^"]*)"', pager.group(0))) if pager else None
    det = len(set(re.findall(r'/comic/index/detail\?video_key=\d+', t)))
    avd = len(set(re.findall(r'/comic/index/avdetail\?video_key=\w+', t)))
    ms = len(set(re.findall(r'/melonshort/video/\d+', t)))
    hl = len(set(re.findall(r'/heiliao-chigua/\w+', t)))
    sets = len(set(re.findall(r'/moviesets/\w+', t)))
    ttl = re.search(r"<title>([^<]*)</title>", t)
    print(f"{path[:60]:62s} HTTP {r.status_code} pager={attrs} det={det} av={avd} ms={ms} hl={hl} set={sets} | {ttl.group(1)[:24] if ttl else ''}")


print("\n===== 各类型分类首页 pager 探测 =====")
probe("/melonshort/cat/amateur")
probe("/melonshort/cat/hunjian")
probe("/%E9%BB%91%E6%96%99%E5%90%83%E7%93%9C/%E4%BB%8A%E6%97%A5%E5%90%83%E7%93%9C/%E6%9C%80%E6%96%B0")
probe("/%E9%BB%91%E6%96%99%E5%90%83%E7%93%9C/%E5%AD%A6%E7%94%9F%E6%A0%A1%E5%9B%AD/%E6%8E%A8%E8%8D%90")
probe("/comic/av/relvideo?model=1&type=theme&order=week")
probe("/comic/av/relvideo?model=107&type=tag&order=week")
probe("/moviesets")
probe("/moviesets/chengrendongman")
probe("/comic/index/video?category=original&page=2")
