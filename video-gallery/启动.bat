@echo off
chcp 65001 >nul
cd /d %~dp0
set VIDEO_SPIDER_DATA=D:\Python\VideoSpider\video_spider\data
.venv\Scripts\python.exe main.py
