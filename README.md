# video-gallery

video_spider 下载视频的展示站：与下载机**完全分离**的独立项目（前后端分离），以只读方式共用其 SQLite 数据库与配置。

![stack](https://img.shields.io/badge/FastAPI-Vue3-blue)

## 功能

- 封面卡片墙：封面图 + 标题 + 标签（最多展示 3 个），角标分类名与文件大小
- 服务端分页（12/24/48 每页）
- 分类（类型）选择：按分组归类的下拉，含每类数量
- 搜索：标题 / video_key 模糊匹配，300ms 防抖
- 在线播放：点卡片弹出播放器（HTTP Range 流式，可拖进度条）；TS 格式浏览器不支持，提供下载按钮

## 共用数据与配置

| 内容 | 来源 |
| --- | --- |
| 数据库 | 与 video_spider 同一个 `spider.db`，**只读**打开（`?mode=ro`），WAL 下与下载机并发互不阻塞 |
| 数据目录 | 复用同一个环境变量 `VIDEO_SPIDER_DATA`（默认 `./data`） |
| 保存位置 | 实时读取 spider 的 `settings.video_dir`，下载机改了保存位置无需重启本服务 |
| 封面 | `DATA_DIR/covers/` 静态挂载在 `/covers` |
| 视频 | `settings.video_dir`（默认 `DATA_DIR/videos`）`/<分类名>/<video_key>.mp4`（回退 `.ts`） |

## 启动

```cmd
uv sync
set VIDEO_SPIDER_DATA=D:\python\video_spider\data   # 指向 spider 数据目录
uv run python main.py                                # 默认 0.0.0.0:8766
```

前端开发：`cd frontend && npm run dev`（Vite 代理 /api、/covers 到 8766）；构建：`npm run build`（产物由 FastAPI 托管）。

## 环境变量

| 变量 | 默认 | 说明 |
| --- | --- | --- |
| `VIDEO_SPIDER_DATA` | `./data` | spider 数据目录（共用） |
| `GALLERY_HOST` / `GALLERY_PORT` | `0.0.0.0` / `8766` | 监听地址端口 |

## API

| 端点 | 说明 |
| --- | --- |
| `GET /api/categories` | 有已完成视频的分类（含数量），按数量降序 |
| `GET /api/videos?category_id=&q=&page=&page_size=` | 服务端分页的视频列表（status=done），q 匹配标题/ID |
| `GET /api/video-file/{id}` | 视频文件流（Range 206）；文件缺失 404 |
| `GET /covers/{file}` | 封面静态文件 |

## 部署（205，192.168.1.205）

部署在 `/opt/video-gallery`，systemd 服务 `video-gallery.service`（端口 8766，`VIDEO_SPIDER_DATA=/mnt/hdd/video-spider-data`，开机自启）。更新流程：

```cmd
cd frontend && npm run build && cd ..
tar -czf %TEMP%\video-gallery.tar.gz --exclude "app/__pycache__" --exclude "*.pyc" app main.py pyproject.toml uv.lock README.md frontend/dist
uv run --with paramiko python scripts/board_ssh.py @n205 put %TEMP%\video-gallery.tar.gz /tmp/video-gallery.tar.gz
uv run --with paramiko python scripts/board_ssh.py @n205 sudo "sh -c 'tar -xzf /tmp/video-gallery.tar.gz -C /opt/video-gallery && chown -R sa:sa /opt/video-gallery && rm -f /tmp/video-gallery.tar.gz && systemctl restart video-gallery'"
```

依赖变更时需在板上 `cd /opt/video-gallery && uv sync --frozen`（前置 `HTTPS_PROXY=http://127.0.0.1:7890`）。
