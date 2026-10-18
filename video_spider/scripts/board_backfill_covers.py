#!/opt/video-spider/.venv/bin/python
"""回填存量视频封面 v2：直接从本地成片抽帧（ffmpeg），不依赖站点 CDN。

- 生成 covers/<video_key>.jpg（5s 处，失败回退首帧）
- 清理旧的 0 字节/横幅错误封面（.gif/.jpeg/.png 旧文件删除，DB 统一指向 .jpg）
- 幂等：已是有效 .jpg 的跳过（--force 重生成）
"""
import re
import sqlite3
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, "/opt/video-spider")
from app import db  # noqa: E402

db.init()
DATA = Path(db.get_settings().get("video_dir") or "").parent if db.get_settings().get(
    "video_dir") else Path("/mnt/hdd/video-spider-data")
force = "--force" in sys.argv


def safe_name(name: str) -> str:
    return re.sub(r'[\\/:*?"<>|]', "", name).strip() or "unknown"


conn = sqlite3.connect(f"{DATA}/spider.db", timeout=15)
conn.row_factory = sqlite3.Row
rows = conn.execute(
    """SELECT v.id, v.video_key, v.cover_path, c.name AS cat
       FROM videos v JOIN categories c ON c.id = v.category_id WHERE v.status='done'""").fetchall()
print(f"待处理 {len(rows)} 个视频")

root = Path(DATA) / "videos"
covers = Path(DATA) / "covers"
done = skipped = failed = 0
for r in rows:
    jpg = covers / f"{r['video_key']}.jpg"
    if jpg.exists() and jpg.stat().st_size > 1000 and not force:
        if r["cover_path"] == f"covers/{r['video_key']}.jpg":
            skipped += 1
            continue
    f = None
    for ext in (".mp4", ".ts"):
        p = root / safe_name(r["cat"]) / f"{r['video_key']}{ext}"
        if p.is_file():
            f = p
            break
    if not f:
        print(f"FAIL(no-file) {r['video_key']}")
        failed += 1
        continue
    # 清掉旧错误封面
    if r["cover_path"]:
        old = Path(DATA) / r["cover_path"]
        if old.suffix != ".jpg" and old.exists():
            old.unlink()
    ok = False
    for ss in ("00:00:05", "0"):
        r2 = subprocess.run(
            ["ffmpeg", "-y", "-loglevel", "error", "-ss", ss, "-i", str(f),
             "-frames:v", "1", "-q:v", "3", str(jpg)], capture_output=True, timeout=120)
        if r2.returncode == 0 and jpg.exists() and jpg.stat().st_size > 1000:
            ok = True
            break
        jpg.unlink(missing_ok=True)
    if not ok:
        print(f"FAIL(ffmpeg) {r['video_key']}")
        failed += 1
        continue
    with conn:
        conn.execute("UPDATE videos SET cover_path=? WHERE id=?",
                     (f"covers/{r['video_key']}.jpg", r["id"]))
    print(f"OK {r['video_key']} {jpg.stat().st_size}B")
    done += 1

print(f"完成：生成 {done}，跳过 {skipped}，失败 {failed}")
