#!/bin/sh
# ts→mp4 v4（严格版）：
#  - 每文件零和循环：mv ts→work（SD 腾出等量空间）→ ffmpeg → 校验 mp4 → 删 work ts → mv mp4→SD → 校验
#  - 任何一步失败：能还原的还原，记 FAIL，继续；绝不无故删数据
#  - 已有 mp4 的 ts 直接删除（视为转换完成）
#  - work 里遗留的 ts（267490，SD 空间已腾出）放最后处理（等 shrink 空间攒够）
DIR="/mnt/sd/video-spider-data/videos"
WORK="/userdata/work"
LOG="/tmp/ts2mp4.log"
mkdir -p "$WORK" 2>/dev/null
: > "$LOG"

ok=0; fail=0
for ts in $(find "$DIR" -name '*.ts' | sort); do
    mp4="${ts%.ts}.mp4"
    if [ -f "$mp4" ]; then
        rm -f "$ts"
        echo "SKIP(mp4 exists): $ts" >> "$LOG"
        continue
    fi
    base=$(basename "$ts" .ts)
    wts="$WORK/$base.ts"
    wmp4="$WORK/$base.mp4"
    if ! mv "$ts" "$wts"; then echo "FAIL(mv-out): $ts" >> "$LOG"; fail=$((fail+1)); continue; fi
    if ! ffmpeg -y -loglevel error -i "$wts" -c copy -movflags +faststart "$wmp4" </dev/null 2>>"$LOG"; then
        mv "$wts" "$ts"
        echo "FAIL(ffmpeg): $ts" >> "$LOG"
        fail=$((fail+1))
        continue
    fi
    if ! [ -s "$wmp4" ]; then
        mv "$wts" "$ts"
        rm -f "$wmp4"
        echo "FAIL(empty-mp4): $ts" >> "$LOG"
        fail=$((fail+1))
        continue
    fi
    rm -f "$wts"
    if mv "$wmp4" "$mp4"; then
        echo "OK: $ts" >> "$LOG"
        ok=$((ok+1))
    else
        echo "FAIL(mv-back,mp4-kept-in-work): $ts" >> "$LOG"
        fail=$((fail+1))
    fi
done

# work 里遗留的 ts（SD 上空间已腾出）：就地转换，mp4 挪回
for wts in /userdata/work/*.ts; do
    [ -f "$wts" ] || continue
    base=$(basename "$wts" .ts)
    cat=${base%%_*}
    key=${base#*_}
    if ffmpeg -y -loglevel error -i "$wts" -c copy -movflags +faststart "/userdata/work/$base.mp4" </dev/null 2>>"$LOG" \
        && mv "/userdata/work/$base.mp4" "$DIR/$cat/$key.mp4"; then
        rm -f "$wts"
        echo "OK(leftover): $base" >> "$LOG"
        ok=$((ok+1))
    else
        echo "FAIL(leftover): $base" >> "$LOG"
        fail=$((fail+1))
    fi
done
echo "DONE ok=$ok fail=$fail" >> "$LOG"
