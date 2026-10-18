# 91spider — monorepo

两个子项目共用一个仓库：

- `video-gallery/` — 视频只读相册/播放器（FastAPI + Vue 3），消费 `video_spider` 下载的视频
- `video_spider/` — 抓取 + 下载 + Chrome 扩展（FastAPI + Vue 3 管理后台 + browser ext）

子目录各自保留独立的 git 历史（通过 subtree merge 引入）。