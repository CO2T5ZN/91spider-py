import re
import requests

UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36"
BASE = "https://91porna.com"
s = requests.Session()
s.headers.update({"User-Agent": UA})


def probe(name, url):
    try:
        r = s.get(url, timeout=20)
        html = r.text
        pager = re.search(r'<ul class="pager[^"]*"[^>]*>', html)
        attrs = dict(re.findall(r'data-([\w-]+)="([^"]*)"', pager.group(0))) if pager else None
        det = len(set(re.findall(r'/comic/index/detail\?video_key=(\d+)', html)))
        avd = len(set(re.findall(r'/comic/index/avdetail\?video_key=(\w+)', html)))
        ms = len(set(re.findall(r'/melonshort/video/(\d+)', html)))
        hl = len(set(re.findall(r'/heiliao-chigua/(\w+)', html)))
        ttl = re.search(r"<title>([^<]*)</title>", html)
        print(f"{name}: HTTP {r.status_code} | pager={attrs} | detail={det} av={avd} short={ms} heiliao={hl} | {ttl.group(1)[:30] if ttl else ''}")
    except Exception as e:
        print(f"{name}: FAIL {e}")


probe("video p2", BASE + "/comic/index/video?category=play&page=2")
probe("video hd p1", BASE + "/comic/index/video?category=hd")
probe("relvideo p2", BASE + "/comic/av/relvideo?model=2&type=theme&order=week&page=2")
probe("relvideo order=update", BASE + "/comic/av/relvideo?model=2&type=theme&order=update")
probe("heiliao p2", BASE + "/%E9%BB%91%E6%96%99%E5%90%83%E7%93%9C/%E6%8E%A8%E8%8D%90?page=2")
probe("heiliao 最新", BASE + "/%E9%BB%91%E6%96%99%E5%90%83%E7%93%9C/%E6%9C%80%E6%96%B0")
probe("moviesets p2", BASE + "/moviesets?page=2")
probe("melonshort p2", BASE + "/melonshort/2")
probe("melonshort cat", BASE + "/melonshort/amateur")
probe("melonshort cat p2", BASE + "/melonshort/amateur/2")
probe("melonshort cat ?page", BASE + "/melonshort/amateur?page=2")
probe("search", BASE + "/comic/index/search?keyword=%E6%8E%A2%E8%8A%B1")
