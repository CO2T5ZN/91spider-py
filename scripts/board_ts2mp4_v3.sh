#!/bin/sh
# 存量 TS 批量转 MP4 v3（SD 卡零空间版）：
# SD 卡满无法直接写 mp4，故逐个把 ts 挪到 /userdata/work 转换，成功后把 mp4 挪回原目录。
DIR="/mnt/sd/video-spider-data/videos"
WORK="/userdata/work"
LOG="/tmp/ts2mp4.log"
mkdir -p "$WORK"
: > "$LOG"
ok=0; fail=0
for ts in $(find "$DIR" -name '*.ts' | sort); do
    base=$(basename "$ts" .ts)
    catdir=$(basename "$(dirname "$ts")")
    wts="$WORK/${catdir}_${base}.ts"
    wmp4="$WORK/${catdir}_${base}.mp4"
    dstmp4="$(dirname "$ts")/${base}.mp4"
    mv "$ts" "$wts"
    if ffmpeg -y -loglevel error -i "$wts" -c copy -movflags +faststart "$wmp4" </dev/null 2>>"$LOG"; then
        mv "$wmp4" "$dstmp4"
        rm -f "$wts"
        echo "OK: $ts" >> "$LOG"
        ok=$((ok+1))
    else
        rm -f "$wmp4"
        mv "$wts" "$ts"   # 转换失败把 ts 放回原位
        echo "FAIL: $ts" >> "$LOG"
        fail=$((fail+1))
    fi
done
rmdir "$WORK" 2>/dev/null
echo "DONE ok=$ok fail=$fail" >> "$LOG"
