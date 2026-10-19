"""一次性封面修复：删除站点占位封面（按内容 md5 判重），从视频随机抽帧重新生成。

用法（板上数据目录）:
  python3 backfill_covers.py --data /mnt/disk2/video-spider-data [--cover-cache /opt/video-gallery/.cover-cache] [--dry-run]

处理逻辑:
  1. covers/ 下按 md5 分组，同组多张（含零字节空文件）视为占位图，全部删除；
  2. 受影响视频（cover_path 指向被删文件）若视频文件在盘：ffprobe 取时长，随机时刻
     抽帧写到原封面同名文件（DB 的 cover_path 不变）；视频缺失或抽帧失败则置
     cover_path=NULL（前端显示"无封面"）；
  3. cover_path 为空/NULL 的视频：生成 covers/{video_key}.jpg 并回写 cover_path；
  4. 同步删除 gallery 封面缓存（--cover-cache 目录）中对应文件，避免继续命中旧占位图。

  --regen-dark：站点还有"纯黑画面"型占位图，每张内容唯一（md5 判重抓不到），
  按 ffmpeg signalstats 平均亮度 YAVG 判定后同样从视频重抽亮帧替换（重生成
  失败保留原图，不置 NULL）。抽帧带亮度校验，偏暗时换时刻重试，避免产出新黑帧。

依赖: 仅标准库 + ffprobe/ffmpeg（板上 /usr/bin）。
"""

from __future__ import annotations

import argparse
import hashlib
import random
import re
import shutil
import sqlite3
import subprocess
import sys
from pathlib import Path

UNSAFE = re.compile(r'[\\/:*?"<>|]')


def safe_name(name: str) -> str:
    """与 spider manager._safe_name / gallery paths.safe_name 保持一致。"""
    return UNSAFE.sub("", name).strip() or "unknown"


def md5_of(path: Path) -> str:
    h = hashlib.md5()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 16), b""):
            h.update(chunk)
    return h.hexdigest()


def ffprobe_duration(video: Path) -> float | None:
    try:
        r = subprocess.run(
            ["ffprobe", "-v", "error", "-show_entries", "format=duration",
             "-of", "csv=p=0", str(video)],
            capture_output=True, text=True, timeout=60,
        )
        return float(r.stdout.strip())
    except (OSError, ValueError, subprocess.TimeoutExpired):
        return None


def luma_of(path: Path) -> float | None:
    """ffmpeg signalstats 计算整幅平均亮度 YAVG（0-255），近似黑图判定；失败返回 None。"""
    try:
        r = subprocess.run(
            ["ffmpeg", "-v", "info", "-i", str(path),
             "-vf", "signalstats,metadata=print:key=lavfi.signalstats.YAVG",
             "-f", "null", "-"],
            capture_output=True, text=True, timeout=60,
        )
    except (OSError, subprocess.TimeoutExpired):
        return None
    m = re.search(r"YAVG=([0-9.]+)", r.stderr)
    return float(m.group(1)) if m else None


def grab_frame(video: Path, out_jpg: Path, duration: float,
               min_luma: float | None = None, tries: int = 6) -> bool:
    """在 [1s, duration-1s] 随机抽帧；min_luma 给定时跳过过暗的帧（避免黑帧封面），
    全部偏暗则保留最亮的一张。"""
    stamps = [random.uniform(1.0, max(1.5, duration - 1)) for _ in range(tries)]
    stamps.append(1.0)
    best: tuple[float, Path] | None = None
    for t in stamps:
        tmp = out_jpg.with_suffix(f".{random.randrange(1 << 30)}.part.jpg")
        try:
            r = subprocess.run(
                ["ffmpeg", "-y", "-v", "error", "-ss", f"{t:.2f}", "-i", str(video),
                 "-frames:v", "1", "-vf", "scale=min(720\\,iw):-2", "-q:v", "3",
                 str(tmp)],
                capture_output=True, timeout=120,
            )
            if r.returncode == 0 and tmp.stat().st_size > 0:
                if min_luma is None:
                    tmp.replace(out_jpg)
                    if best is not None:
                        best[1].unlink(missing_ok=True)
                    return True
                lum = luma_of(tmp) or 0.0
                if lum >= min_luma:
                    tmp.replace(out_jpg)
                    if best is not None:  # 达标即收工，清掉此前攒的暗帧候选
                        best[1].unlink(missing_ok=True)
                    return True
                if best is None or lum > best[0]:
                    if best is not None:
                        best[1].unlink(missing_ok=True)
                    best = (lum, tmp)
                    continue
        except (OSError, subprocess.TimeoutExpired):
            pass
        tmp.unlink(missing_ok=True)
    if best is not None:  # 整支视频都偏暗，用最亮的一张兜底
        best[1].replace(out_jpg)
        return True
    return False


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--data", required=True, help="数据目录（含 spider.db/covers/videos）")
    ap.add_argument("--cover-cache", default=None, help="gallery 封面 SSD 缓存目录（可选）")
    ap.add_argument("--regen-dark", action="store_true",
                    help="额外扫描现有封面：平均亮度 YAVG < --luma-min 的视为站点黑图占位，"
                         "从视频重抽亮帧替换（同名覆盖，cover_path 不变）")
    ap.add_argument("--luma-min", type=float, default=30.0, help="近黑判定阈值（0-255）")
    ap.add_argument("--dark-size-limit", type=int, default=0,
                    help="只检查小于该字节数的封面（黑图压缩后极小，可省全量扫描），0=全部检查")
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()

    data = Path(args.data)
    covers = data / "covers"
    cache = Path(args.cover_cache) if args.cover_cache else None
    if not covers.is_dir():
        print(f"covers 目录不存在: {covers}")
        return 1

    db = sqlite3.connect(data / "spider.db")
    db.row_factory = sqlite3.Row
    settings = {k: v for k, v in db.execute("SELECT key, value FROM settings")}

    # 视频根目录探测顺序与 paths.video_roots() 一致
    roots: list[Path] = []
    for line in re.split(r"[\r\n;]+", settings.get("video_dirs") or ""):
        if line.strip():
            roots.append(Path(line.strip()))
    if (settings.get("video_dir") or "").strip():
        roots.append(Path(settings["video_dir"].strip()))
    roots.append(data / "videos")

    def find_video(category: str, video_key: str) -> Path | None:
        base = safe_name(category)
        for root in roots:
            for ext in (".mp4", ".ts"):
                p = root / base / f"{video_key}{ext}"
                if p.is_file():
                    return p
        return None

    # 1. 按内容判重，找出占位图（同组 >=2 张，或零字节空文件）
    by_hash: dict[str, list[str]] = {}
    for f in sorted(covers.iterdir()):
        if not f.is_file():
            continue
        by_hash.setdefault(md5_of(f) if f.stat().st_size else "<empty>", []).append(f.name)
    placeholder_names: set[str] = set()
    for h, names in by_hash.items():
        if h == "<empty>" or len(names) > 1:
            placeholder_names.update(names)
    print(f"占位图（重复组/空文件）共 {len(placeholder_names)} 个 / {len(by_hash)} 种内容")

    # 2. 删除占位图；受影响视频待重生成
    rows = db.execute(
        """SELECT v.id, v.video_key, v.cover_path, c.name AS category
           FROM videos v JOIN categories c ON c.id = v.category_id"""
    ).fetchall()
    name_to_row = {}
    for r in rows:
        if r["cover_path"]:
            name_to_row[r["cover_path"].split("/")[-1]] = r

    to_regen: list[sqlite3.Row] = []
    orphans = 0
    for name in sorted(placeholder_names):
        if name in name_to_row:
            to_regen.append(name_to_row[name])
        else:
            orphans += 1  # 无 DB 记录指向，直接删
        if not args.dry_run:
            (covers / name).unlink(missing_ok=True)

    # 3. cover_path 为空的视频也补封面
    no_cover = [r for r in rows if not r["cover_path"]]

    # 4. 近黑封面扫描（站点的黑图占位每张内容唯一，md5 判重抓不到，按亮度判）
    work = [(r, r["cover_path"].split("/")[-1], False) for r in to_regen] + \
           [(r, f"{r['video_key']}.jpg", False) for r in no_cover]
    if args.regen_dark:
        dark = orphan_dark = 0
        for f in sorted(covers.iterdir()):
            if not f.is_file() or f.stat().st_size == 0:
                continue
            if args.dark_size_limit and f.stat().st_size > args.dark_size_limit:
                continue
            lum = luma_of(f)
            if lum is None or lum >= args.luma_min:  # 0.0 是合法值（纯黑），不能 or 默认值
                continue
            row = name_to_row.get(f.name)
            if row:
                work.append((row, f.name, True))  # 重生成失败时保留原图，不置 NULL
                dark += 1
            else:
                orphan_dark += 1
                if not args.dry_run:
                    f.unlink(missing_ok=True)
        print(f"近黑封面（YAVG<{args.luma_min}）共 {dark} 个待重生成，孤儿黑图 {orphan_dark} 个")

    # 5. 重生成
    luma_min = args.luma_min if args.regen_dark else None
    regen_ok = regen_fail = skipped_novideo = 0
    updates: list[tuple[str, tuple]] = []  # (sql, params) 延迟到非 dry-run 时提交
    for r, jpg_name, keep_on_fail in work:
        video = find_video(r["category"], r["video_key"])
        if not video:
            skipped_novideo += 1
            if r["cover_path"] and not keep_on_fail:
                updates.append(("UPDATE videos SET cover_path=NULL WHERE id=?", (r["id"],)))
            continue
        dur = ffprobe_duration(video)
        if dur is None:
            regen_fail += 1
            continue
        out = covers / jpg_name
        if args.dry_run:
            regen_ok += 1
            continue
        if grab_frame(video, out, dur, min_luma=luma_min):
            regen_ok += 1
            if not r["cover_path"]:
                updates.append(("UPDATE videos SET cover_path=? WHERE id=?",
                                (f"covers/{jpg_name}", r["id"])))
            if cache:
                (cache / jpg_name).unlink(missing_ok=True)
        else:
            regen_fail += 1
            if r["cover_path"] and not keep_on_fail:
                updates.append(("UPDATE videos SET cover_path=NULL WHERE id=?", (r["id"],)))

    if not args.dry_run:
        for sql, params in updates:
            db.execute(sql, params)
        db.commit()

    print(f"重生成 {regen_ok}，失败 {regen_fail}，视频缺失跳过 {skipped_novideo}，"
          f"无记录孤儿占位 {orphans}，DB 更新 {len(updates)} 条"
          f"{'（dry-run，未实际执行）' if args.dry_run else ''}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
