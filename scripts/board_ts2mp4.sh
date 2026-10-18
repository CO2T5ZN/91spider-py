#!/bin/sh
# 存量 TS 批量转 MP4 v2：捕获 ffmpeg stderr 进日志，成功即删 ts。
DIR="/mnt/sd/video-spider-data/videos"
LOG="/tmp/ts2mp4.log"
: > "$LOG"
echo "PATH=$PATH" >> "$LOG"
echo "which=$(which ffmpeg 2>&1)" >> "$LOG"
ok=0; fail=0
for ts in $(find "$DIR" -name '*.ts' | sort); do
    mp4="${ts%.ts}.mp4"
    if ffmpeg -y -loglevel error -i "$ts" -c copy -movflags +faststart "$mp4" </dev/null 2>>"$LOG"; then
        rm -f "$ts"
        echo "OK: $ts" >> "$LOG"
        ok=$((ok+1))
    else
        rm -f "$mp4"
        echo "FAIL: $ts" >> "$LOG"
        fail=$((fail+1))
    fi
done
echo "DONE ok=$ok fail=$fail" >> "$LOG"
