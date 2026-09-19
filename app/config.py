"""全局配置：数据目录（与 video_spider 共用）、端口。"""

import os
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent

# 与 video_spider 共用同一环境变量：指向 spider 的数据目录（含 spider.db、covers/、videos/）
DATA_DIR = Path(os.environ.get("VIDEO_SPIDER_DATA", PROJECT_ROOT / "data"))
DB_PATH = DATA_DIR / "spider.db"
COVER_DIR = DATA_DIR / "covers"

HOST = os.environ.get("GALLERY_HOST", "0.0.0.0")
PORT = int(os.environ.get("GALLERY_PORT", "8766"))

FRONTEND_DIST = PROJECT_ROOT / "frontend" / "dist"
