"""页面解析：首页分类提取（XPath）、pager 计数、列表页条目、详情页 m3u8（待逆向）。"""

from __future__ import annotations

import html as html_lib
import re
import urllib.parse

from lxml import etree

from .. import config

# ---------------------------------------------------------------- 分类类型

_TYPE_RULES: list[tuple[str, re.Pattern]] = [
    ("video", re.compile(r"^/comic/index/video\?category=")),
    ("search", re.compile(r"^/comic/index/search\?")),
    ("av", re.compile(r"^/comic/av/relvideo\?")),
    ("melonshort", re.compile(r"^/melonshort/")),
    ("heiliao", re.compile(r"^/(?:%E9%BB%91%E6%96%99%E5%90%83%E7%93%9C|黑料吃瓜)/")),
    ("movieset", re.compile(r"^/moviesets(?:/|$)")),
    ("novel", re.compile(r"^/novels(?:/|$)")),
]
_NOT_DOWNLOADABLE = {"novel", "external", "other", "movieset", "manual"}


def classify_path(path: str) -> str:
    for ctype, pat in _TYPE_RULES:
        if pat.match(path):
            return ctype
    if path.startswith(("http://", "https://")):
        return "external"
    if path.startswith(("/comic/index/links", "/comic/index/more")):
        return "other"
    return "other"


def is_downloadable(ctype: str) -> bool:
    return ctype not in _NOT_DOWNLOADABLE


# ---------------------------------------------------------------- 首页分类

def parse_home_categories(html: str) -> list[dict]:
    """首页 video-sub-item 提取：名称、路径、分组。"""
    tree = etree.HTML(html)
    out, seen = [], set()
    for a in tree.xpath(config.CATEGORY_XPATH):
        href = (a.get("href") or "").strip()
        name = "".join(a.xpath(".//text()")).strip()
        if not href or not name or href in seen:
            continue
        seen.add(href)
        path = href if href.startswith("http") else href.split("#")[0]
        # 分组标题：video-sub-menu 前一个兄弟 app-nav-item 的文本（class 是多值）
        group = None
        nav = a.xpath('ancestor::*[contains(concat(" ", normalize-space(@class), " "), '
                      '" video-sub-menu ")]/preceding-sibling::a['
                      'contains(concat(" ", normalize-space(@class), " "), " app-nav-item ")][1]')
        if nav:
            group = "".join(nav[0].xpath(".//text()")).strip() or None
        full = href if href.startswith("http") else config.BASE_URL + href
        out.append({
            "name": name,
            "path": path,
            "href": href,
            "url": full,
            "group": group,
            "type": classify_path(href),
            "enabled": is_downloadable(classify_path(href)),
        })
    return out


# ---------------------------------------------------------------- pager 计数

def parse_pager(html: str) -> dict | None:
    """取 dx-pager 的 data-rec-total / data-rec-per-page / data-page。"""
    tree = etree.HTML(html)
    ul = tree.xpath('//ul[contains(concat(" ", normalize-space(@class), " "), " pager ")]')
    if not ul:
        return None
    attrs = dict(ul[0].attrib)
    total = attrs.get("data-rec-total")
    per = attrs.get("data-rec-per-page")
    return {
        "page": int(attrs["data-page"]) if attrs.get("data-page", "").isdigit() else None,
        "rec_total": int(total) if total and total.isdigit() else None,
        "rec_per_page": int(per) if per and per.isdigit() else None,
    }


def page_url(path: str, page: int) -> str:
    """按分类路径生成第 page 页 URL（melonshort 翻页机制未逆向，仅第 1 页）。"""
    url = path if path.startswith("http") else config.BASE_URL + path
    if page <= 1:
        return url
    sep = "&" if "?" in url else "?"
    return f"{url}{sep}page={page}"


# ---------------------------------------------------------------- 列表页条目

_ITEM_RULES: dict[str, re.Pattern] = {
    "video": re.compile(r"^(/comic/index/detail\?video_key=(\d+))$"),
    "search": re.compile(r"^(/comic/index/detail\?video_key=(\d+))$"),
    "av": re.compile(r"^(/comic/index/avdetail\?video_key=(\w+))$"),
    "melonshort": re.compile(r"^(/melonshort/video/(\d+))$"),
    "heiliao": re.compile(r"^(/heiliao-chigua/(\w+))$"),
}


def parse_list_items(html: str, ctype: str, page_path: str) -> list[dict]:
    """列表页 -> 视频条目 (video_key, detail_url, title)。按分类类型匹配对应链接模式。

    同一视频常被多个锚点包裹（海报链接/标题链接/排行榜链接），按 video_key 聚合，
    跳过排行榜徽标类的垃圾文本（top-N、纯名次数字、时长），取首个有效标题。
    """
    pat = _ITEM_RULES.get(ctype)
    if not pat:
        return []
    tree = etree.HTML(html)
    best: dict[str, dict] = {}
    order: list[str] = []
    for a in tree.xpath(f'//a[contains(@href, "{_href_marker(ctype)}")]'):
        href = (a.get("href") or "").split("#")[0]
        m = pat.match(href)
        if not m:
            continue
        full_path, key = m.group(1), m.group(2)
        if key not in best:
            best[key] = {"video_key": key,
                         "detail_url": config.BASE_URL + full_path,
                         "title": None}
            order.append(key)
        if best[key]["title"]:
            continue
        t = _extract_title(a)
        if is_clean_title(t):
            best[key]["title"] = t
    return [best[k] for k in order]


# 排行榜徽标 / 名次数字 / 时长 等非标题文本
_JUNK_TITLE_RE = re.compile(r"^(top[-_ ]?\d+|\d{1,3}|\d{1,2}:\d{2}(:\d{2})?)$", re.I)


def is_clean_title(title: str | None) -> bool:
    if not title:
        return False
    t = title.strip()
    if not t:
        return False
    return not _JUNK_TITLE_RE.match(t)


def extract_detail_meta(html: str) -> dict:
    """详情页 -> 结构化元数据：真实标题、封面 URL、标签列表。

    og:image 指向 expose.eisees.com（仅元数据用，该 CDN 对非浏览器请求返回 200 空内容，
    不能作为图片源）；成片封面统一由下载完成后 ffmpeg 从视频抽帧生成（见 manager）。
    标签取多个 <meta property="video:tag">，去重保序。
    """
    meta = {"title": None, "cover_url": None, "tags": []}
    m = re.search(r'<meta[^>]+property="og:image"[^>]+content="([^"]+)"', html)
    if m:
        meta["cover_url"] = html_lib.unescape(m.group(1)).strip() or None
    tags = re.findall(r'<meta[^>]+property="video:tag"[^>]+content="([^"]+)"', html)
    seen = set()
    for t in tags:
        t = html_lib.unescape(t).strip()
        if t and t not in seen:
            seen.add(t)
            meta["tags"].append(t)
    meta["title"] = extract_detail_title(html)
    return meta


def extract_detail_title(html: str) -> str | None:
    """详情页 -> 真实标题（og:title / h1），用于修正列表页残留的空/脏标题。"""
    m = re.search(r'<meta[^>]+property="og:title"[^>]+content="([^"]+)"', html)
    if m:
        t = html_lib.unescape(m.group(1)).strip()
        return t or None
    m = re.search(r"<h1[^>]*>(.*?)</h1>", html, re.S)
    if m:
        t = re.sub(r"<[^>]+>", "", m.group(1)).strip()
        return t or None
    return None


def _href_marker(ctype: str) -> str:
    return {
        "video": "/comic/index/detail?video_key=",
        "search": "/comic/index/detail?video_key=",
        "av": "/comic/index/avdetail?video_key=",
        "melonshort": "/melonshort/video/",
        "heiliao": "/heiliao-chigua/",
    }.get(ctype, "\x00")


def _extract_title(a) -> str | None:
    """按优先级取标题：title 属性 -> 所有 img alt -> 所有文本节点。

    每类候选都可能混入排行榜徽标（alt="top-1"/alt="4"）等垃圾值，
    逐一校验，返回首个有效标题。
    """
    title = a.get("title")
    if is_clean_title(title):
        return title.strip()
    for alt in a.xpath(".//img/@alt"):
        if is_clean_title(alt):
            return alt.strip()
    for t in a.xpath(".//text()"):
        if is_clean_title(t):
            return t.strip()
    return None


# ---------------------------------------------------------------- 详情页 m3u8

# 逆向结论（scripts/probe_detail_play.py / probe_m3u8_real.py）：
# 详情页内联脚本经 Dean Edwards packer 混淆，document.write 加载
# /index/detail_play?img=<封面路径>&ads=&u=<160位hex令牌>&h=&t=<时间桶>
# 该动态脚本返回的 packer 字典中含明文 m3u8 地址（带 CDN auth_key，约几分钟时效）。
# 实测仅 u 令牌必需：img 可为空、t 可为 0、无需 Referer。
# m3u8 为 AES-128 加密（EXT-X-KEY），分片下载后需解密（见 downloader/m3u8.py）。


def extract_m3u8_url(html: str, page_url_: str, client=None) -> str | None:
    """详情页 -> m3u8 播放地址（绝对 URL），失败返回 None。"""
    # 1) 明文兜底（melonshort 详情页直接内嵌；注意 HTML 转义的 &amp;）
    m = re.search(r'https?://[^"\'\s\\|]+\.m3u8\?[^"\'\s\\|]*', html)
    if m:
        return urllib.parse.urljoin(page_url_, html_lib.unescape(m.group(0)))

    if client is None:
        return None

    # 2) detail_play 流程：u 令牌（长 hex），img 取 og:image 路径或留空
    tokens = re.findall(r"[0-9a-f]{100,}", html)
    img = ""
    og = re.search(r'<meta[^>]+property="og:image"[^>]+content="([^"]+)"', html)
    if og:
        img = urllib.parse.quote(urllib.parse.urlsplit(og.group(1)).path, safe="/")
    play_path = "/index/detail_play"
    for u in tokens[:3]:
        try:
            body = client.get_text(f"{config.BASE_URL}{play_path}?img={img}&ads=&u={u}&h=&t=0")
        except Exception:  # noqa: BLE001 - 网络失败换下一个候选
            continue
        m = re.search(r"https?://[^'\"|]+\.m3u8\?[^'\"|]*", body)
        if m:
            return html_lib.unescape(m.group(0))
    return None
