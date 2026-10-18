# video-spider — 91porna 视频爬虫

Web 面板驱动的视频爬虫：分类提取 → 视频列表枚举 → 详情页解析 m3u8 → 分片多线程下载（AES-128 解密、断点续传）→ 合并单文件。
后端 Python (FastAPI + SQLite + SSE)，前端 Vue 3 + Ant Design Vue。

## 当前状态

✅ 全链路已打通并实测：
- **分类数据抓取**：XPath 提取首页全部分类（含分组/类型/路径），抓取各分类第 1 页
  dx-pager 得到精确视频总数（`data-rec-total`）。melonshort 分类页为 AJAX 列表无静态
  pager，计数为"未知"（其视频详情页可正常下载）。
- **详情页 m3u8 解析**（4 种详情页类型均实测通过）：
  1. 详情页内联脚本为 Dean Edwards packer，解包后可见其 `document.write` 加载
     `/index/detail_play?img=<封面>&ads=&u=<160位hex令牌>&h=&t=<时间桶>`；
  2. 该动态脚本返回的 packer 字典中含**明文 m3u8 地址**（CDN auth_key 约 7 分钟时效）；
  3. 实测仅 `u` 令牌必需（img 可空、t 可为 0、无需 Referer）；
  4. melonshort 详情页直接内嵌 m3u8，无需 detail_play 流程。
- **下载**：m3u8 为 AES-128 加密（EXT-X-KEY + 显式 IV），分片下载后 AES-128-CBC 解密
  （cryptography），PKCS7 去填充，按序二进制合并为 .ts 单文件。
- **断点续传**：视频级（重启自动暂停→继续）+ 分片级（已下载分片跳过）；因 CDN auth_key
  短时效，续传时自动重新解析 m3u8 换取新 URL，已完成分片不受影响。
- **按页加载**：列表枚举不预读——下载完当前页的全部视频后才抓取下一页
  （分类计数同步不受影响，仍只抓第 1 页取 pager 数据）。
- **Web 面板**：分类同步/搜索/建任务、任务进度条/线程数运行中调整/启停/重试失败/视频抽屉，
  全部动态内容走 SSE 推送，无前端轮询。

## 启动

```bash
# 后端依赖
uv sync

# 前端（首次需构建，产物由后端直接托管在单端口）
cd frontend
npm install
npm run build
cd ..

# 启动（默认 http://127.0.0.1:8765）
uv run python main.py
```

前端开发模式（热更新，代理 /api 到 8765）：`cd frontend && npm run dev` 后访问 5173。

## 使用流程

1. 打开面板 → 「分类管理」→ 点 **同步分类**（约 55 个分类，40+ 请求抓计数，进度实时可见）。
2. 在目标分类行点 **下载任务** → 设线程数 → 创建并启动。
3. 「下载任务」页查看进度；可运行中调整线程数、暂停/继续/停止、重试失败项。

## 目录结构

```
app/
  config.py            站点、目录、默认参数
  db.py                SQLite（WAL）+ 全部 DAO
  events.py            SSE 事件中心（线程安全发布）
  scraper/
    client.py          httpx 客户端（限速/重试）
    parser.py          分类 XPath、pager、列表条目、详情 m3u8 桩位
    category_sync.py   分类同步任务（并发抓计数）
  downloader/
    pool.py            动态线程池（运行中 resize）
    m3u8.py            m3u8 解析（含 master 变体选择、AES 检测）与分片合并
    manager.py         任务生命周期、列表枚举、断点续传流水线
  api/routes.py        REST + GET /api/events (SSE)
  main.py              FastAPI 组装 + 前端静态托管（SPA 回退）
frontend/              Vue3 + AntD 面板源码（Vite）
scripts/               站点结构探查脚本（逆向过程留档）
data/                  运行数据：spider.db、tmp/ 分片、videos/ 成片
```

## 断点续传说明

- 视频级：`videos.status` 记录 pending/downloading/done/failed；服务重启时自动把
  运行中任务置为「已暂停」，进行中的视频退回队列，点「继续」即恢复。
- 分片级：每个分片一行记录，完成的分片跳过；分片先写 `.part` 再原子改名。
- 合并产物：`data/videos/<分类名>/<video_key>.ts`（TS 流直接二进制拼接）。

## 浏览器插件（一键提交下载）

`extension/` 目录是 Chrome 插件（Manifest V3）：在视频详情页自动显示圆形浮标按钮，
点击即把当前视频提交给本服务的**单线程队列**下载。

安装：
1. Chrome 打开 `chrome://extensions` → 开启「开发者模式」→「加载已解压的扩展程序」→ 选择 `extension/` 目录。
2. 确认后端已启动（默认 `http://127.0.0.1:8765`，可在扩展「选项」页修改地址）。
3. 打开任意视频详情页（`/comic/index/detail`、`/comic/index/avdetail`、`/melonshort/video/*`、`/heiliao-chigua/*`），
   右下角出现浮标按钮。

按钮状态：
| 显示 | 含义 |
|------|------|
| 灰色 × | 后端未连接 |
| 白色 ↓ | 未下载，点击提交 |
| 黄色 … + 黄环 | 排队中（外环显示当前下载进度） |
| 绿环 + ↓ + 红色角标 | 下载中（外环=该视频分片进度，角标=队列正在下载的数量） |
| 绿色 ✓ | 已下载完成（再次点击无效） |
| 红色 ! | 下载失败，点击可重试 |

说明：
- 提交按 `(分类, video_key)` 幂等去重：已下载/排队中的视频重复提交无副作用。
- 插件队列在面板中显示为「手动提交」分类的任务，**固定单线程**（API 拒绝调整线程数）。
- 悬停按钮可查看状态提示（队列长度、分片进度、失败原因）。

## 事件一览（SSE `event` 名）

| event       | 载荷                                    | 用途                     |
|-------------|-----------------------------------------|--------------------------|
| `sync`      | `{phase, done, total, ...}`             | 分类同步进度             |
| `categories`| `{category: {...行}}`                   | 单行分类更新             |
| `task`      | `{task: {...行, progress}}`             | 任务状态/进度            |
| `video`     | `{id, status, done_segments, ...}`      | 视频/分片进度            |
| `log`       | `{level, message}`                      | 后端日志                 |

连接地址 `GET /api/events`；15s 心跳；断线自动重连（EventSource 原生）。
