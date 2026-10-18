"""单视频端到端小样：解析 m3u8 -> 下载3片 -> AES解密 -> 校验TS头"""

import sys
import tempfile
from pathlib import Path

sys.path.insert(0, r"D:\python\video_spider")

from app import db
from app.scraper import parser
from app.scraper.client import SiteClient
from app.downloader import m3u8

db.init()
client = SiteClient()
detail_url = "https://91porna.com/comic/index/detail?video_key=412915"
html = client.get_text(detail_url)
print("detail page fetched:", len(html))

m3u8_url = parser.extract_m3u8_url(html, detail_url, client)
print("m3u8:", (m3u8_url or "None")[:140])
assert m3u8_url, "m3u8 解析失败"

pl = m3u8.parse(client.get_text(m3u8_url), m3u8_url)
while pl.is_master:
    print("master ->", pl.variant_url[:120])
    pl = m3u8.parse(client.get_text(pl.variant_url), pl.variant_url)
print(f"segments={len(pl.segments)} key={pl.key_url[:80] if pl.key_url else None} iv={pl.key_iv} media_seq={pl.media_sequence}")

key = client.get_bytes(pl.key_url) if pl.key_url else None
print("key:", key.hex() if key else None, "len", len(key) if key else 0)

tmp = Path(tempfile.mkdtemp(prefix="vs_test_"))
for seg in pl.segments[:3]:
    data = client.get_bytes(seg.url)
    raw_head = data[:4].hex()
    if key is not None:
        data = m3u8.decrypt_segment(data, key, m3u8.segment_iv(pl, seg.seq))
    (tmp / f"seg_{seg.seq:05d}.ts").write_bytes(data)
    sync = b"\x47"
    print(f"seg {seg.seq}: raw={raw_head} dec_head={data[:4].hex()} size={len(data)} TS={'OK' if data[:1] == sync else 'BAD'}")

out = tmp / "merged.ts"
m3u8.merge_segments(tmp, out, 3)
print("merged size:", out.stat().st_size, "head:", out.read_bytes()[:1].hex())
