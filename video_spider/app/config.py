"""全局配置：目录、站点、默认参数。"""

import os
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
DATA_DIR = Path(os.environ.get("VIDEO_SPIDER_DATA", PROJECT_ROOT / "data"))
DB_PATH = DATA_DIR / "spider.db"
TMP_DIR = DATA_DIR / "tmp"        # 分片临时目录（每视频一个子目录）
VIDEO_DIR = DATA_DIR / "videos"   # 合并后的成片目录（按分类子目录）
COVER_DIR = DATA_DIR / "covers"   # 视频封面（下载时抓取）
FRONTEND_DIST = PROJECT_ROOT / "frontend" / "dist"

HOST = os.environ.get("VIDEO_SPIDER_HOST", "127.0.0.1")
PORT = int(os.environ.get("VIDEO_SPIDER_PORT", "8765"))

BASE_URL = "https://91porna.com"
UA = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36"
)

# 首页分类提取 XPath（video-sub-item 为分类链接的 class）
CATEGORY_XPATH = '//a[contains(concat(" ", normalize-space(@class), " "), " video-sub-item ")]'
# 分组标题：video-sub-menu 容器的前一个兄弟节点 app-nav-item
GROUP_ITEM_XPATH = 'ancestor::*[1]/preceding-sibling::a[1]'

DEFAULT_SETTINGS = {
    "default_threads": "3",   # 新建任务的默认线程数
    "sync_workers": "4",      # 分类计数同步的并发
    "max_list_pages": "50",   # 每个分类最多枚举的列表页数
    "request_delay": "0.15",  # 同主机请求最小间隔（秒）
    "keep_segments": "0",     # 合并成功后是否保留分片
    "video_dir": "",          # 合并视频保存根目录；空 = 默认 VIDEO_DIR（实时生效，无需重启）
    "video_dirs": "",         # 候选保存根目录列表（每行/分号一个），多硬盘支持
    "video_root_default": "", # 固定默认保存盘；空 = 每个视频动态选剩余空间最大的可写盘
    "auto_retry_failed": "1", # 任务正常完成后自动把失败视频重试一遍（仅一遍）
    "daily_update": "1",      # 每日增量检查已完成任务：对比站点列表，新增则自动下载
    "daily_update_time": "04:00",  # 每日增量检查时刻 HH:MM
    "output_format": "mp4",   # 最终产物格式：mp4（ffmpeg 转封装，失败保留 ts）| ts
}

for d in (DATA_DIR, TMP_DIR, VIDEO_DIR, COVER_DIR):
    d.mkdir(parents=True, exist_ok=True)
