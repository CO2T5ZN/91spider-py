"""快速找详情页里 AJAX 播放接口的线索（供后续阶段参考）"""

import re
import requests

UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36"
BASE = "https://91porna.com"
s = requests.Session()
s.headers.update({"User-Agent": UA})
r = s.get(BASE + "/comic/index/detail?video_key=412915", timeout=25)
t = r.text

for pat in [r'/comic/[a-z/]+play[^"\']*', r'ajax[^"\';]{0,60}', r'xmlhttp|XMLHttpRequest|axios|\.get\(["\'][^"\']+["\']',
            r'hls|Hls|m3u8|playurl|play_url|getVideo|get_video', r'<script[^>]*src="([^"]+)"']:
    hits = re.findall(pat, t)
    print(f"{pat[:44]:46s} -> {len(hits)}", list(dict.fromkeys(hits))[:6])

# script src 列表
for m in re.findall(r'<script[^>]*src="([^"]+)"', t)[:15]:
    print("script:", m)
