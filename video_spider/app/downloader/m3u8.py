"""m3u8 解析、AES-128 解密与合并。"""

from __future__ import annotations

import logging
import re
import urllib.parse
from dataclasses import dataclass, field
from pathlib import Path

from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes

log = logging.getLogger("spider.m3u8")


class M3u8Error(Exception):
    pass


class UnsupportedEncryption(M3u8Error):
    """仅支持 AES-128（HLS 标准）；SAMPLE-AES 等不支持。"""


@dataclass
class Segment:
    seq: int
    url: str


@dataclass
class Playlist:
    segments: list[Segment] = field(default_factory=list)
    is_master: bool = False
    variant_url: str | None = None    # master 时带宽最高的子播放列表
    key_url: str | None = None        # EXT-X-KEY METHOD=AES-128 的密钥地址
    key_iv: str | None = None         # 显式 IV（0x hex），缺省用 media_sequence+seq
    media_sequence: int = 0
    map_url: str | None = None        # EXT-X-MAP（fMP4 初始化段）


def parse(text: str, base_url: str) -> Playlist:
    """解析媒体/主播放列表。master 自动挑最高带宽变体。"""
    lines = [ln.strip() for ln in text.splitlines()]
    if not any(ln.startswith("#EXTM3U") for ln in lines):
        raise M3u8Error("不是有效的 m3u8 内容")

    variants: list[tuple[int, str]] = []
    segments: list[Segment] = []
    pl = Playlist()
    stream_bandwidth = 0
    key_info: tuple[str, str | None, str | None] | None = None
    key_active = False  # 当前 KEY 是否对后续分片生效

    for ln in lines:
        if ln.startswith("#EXT-X-STREAM-INF:"):
            m = re.search(r"BANDWIDTH=(\d+)", ln)
            stream_bandwidth = int(m.group(1)) if m else 0
        elif ln.startswith("#EXT-X-MEDIA-SEQUENCE:"):
            pl.media_sequence = int(ln.split(":", 1)[1].strip() or 0)
        elif ln.startswith("#EXT-X-KEY:"):
            attrs = _parse_attrs(ln.split(":", 1)[1])
            method = (attrs.get("METHOD") or "NONE").upper()
            if method == "NONE":
                key_active = False
            elif method == "AES-128":
                uri = attrs.get("URI")
                if not uri:
                    raise M3u8Error("AES-128 KEY 缺少 URI")
                key_info = (method, urllib.parse.urljoin(base_url, uri), attrs.get("IV"))
                key_active = True
            else:
                raise UnsupportedEncryption(f"不支持的加密方式: {method}")
        elif ln.startswith("#EXT-X-MAP:"):
            attrs = _parse_attrs(ln.split(":", 1)[1])
            if attrs.get("URI"):
                pl.map_url = urllib.parse.urljoin(base_url, attrs["URI"])
        elif ln and not ln.startswith("#"):
            if stream_bandwidth or "#EXT-X-STREAM-INF" in text:
                variants.append((stream_bandwidth, urllib.parse.urljoin(base_url, ln)))
                stream_bandwidth = 0
            else:
                if key_active and key_info and pl.key_url is None:
                    pl.key_url, pl.key_iv = key_info[1], key_info[2]
                segments.append(Segment(seq=len(segments),
                                        url=urllib.parse.urljoin(base_url, ln)))

    if variants:
        variants.sort(key=lambda x: x[0], reverse=True)
        pl.is_master = True
        pl.variant_url = variants[0][1]
        return pl
    if segments:
        pl.segments = segments
        return pl
    raise M3u8Error("m3u8 中没有可用的分片")


def _parse_attrs(s: str) -> dict[str, str]:
    out: dict[str, str] = {}
    for m in re.finditer(r'([A-Z0-9-]+)=("([^"]*)"|[^,]*)', s):
        out[m.group(1)] = m.group(3) if m.group(3) is not None else m.group(2).strip()
    return out


def segment_iv(pl: Playlist, seq: int) -> bytes:
    """显式 IV 优先；否则 HLS 规范：(media_sequence + seq) 16 字节大端。"""
    if pl.key_iv:
        hexs = pl.key_iv[2:] if pl.key_iv.lower().startswith("0x") else pl.key_iv
        return bytes.fromhex(hexs.zfill(32))
    return (pl.media_sequence + seq).to_bytes(16, "big")


def decrypt_segment(data: bytes, key: bytes, iv: bytes) -> bytes:
    """AES-128-CBC 解密并去除 PKCS7 填充。"""
    dec = Cipher(algorithms.AES(key), modes.CBC(iv)).decryptor()
    out = dec.update(data) + dec.finalize()
    pad = out[-1] if out else 0
    if 1 <= pad <= 16 and out[-pad:] == bytes([pad]) * pad:
        out = out[:-pad]
    return out


def merge_segments(seg_dir: Path, out_file: Path, count: int, init_file: Path | None = None) -> Path:
    """按序号二进制拼接分片为单文件（TS 流可直接拼接；fMP4 先写 init 段）。"""
    out_file.parent.mkdir(parents=True, exist_ok=True)
    with open(out_file, "wb") as out:
        if init_file and init_file.exists():
            out.write(init_file.read_bytes())
        for seq in range(count):
            p = seg_dir / f"seg_{seq:05d}.ts"
            if not p.exists():
                raise M3u8Error(f"缺少分片文件 {p.name}")
            with open(p, "rb") as f:
                while True:
                    chunk = f.read(1 << 20)
                    if not chunk:
                        break
                    out.write(chunk)
    return out_file
