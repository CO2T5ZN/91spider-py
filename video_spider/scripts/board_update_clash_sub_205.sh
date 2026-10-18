#!/bin/sh
# 更新 clash 订阅（205 版）：经本机代理拉订阅，拼接校验后替换并重启。
# 205 直连不了订阅站，必须走 clash 自身代理。
set -e
SUB_URL="https://sub.o2t5z.cn/clash/qflldxm8sm0jx0au"
DIR="/etc/clash"
TMP=$(mktemp)
TMP_CONFIG="$TMP.config"
trap 'rm -f "$TMP" "$TMP_CONFIG"' EXIT
curl -fsSL -x http://127.0.0.1:7890 -A "clash.meta/v1.19.31" --max-time 60 -o "$TMP" "$SUB_URL"
cat "$DIR/base.yaml" "$TMP" > "$TMP_CONFIG"
/usr/local/bin/clash -t -d "$DIR" -f "$TMP_CONFIG" >/dev/null 2>&1
mv "$TMP_CONFIG" "$DIR/config.yaml"
systemctl restart clash
echo "subscription updated, clash restarted"
