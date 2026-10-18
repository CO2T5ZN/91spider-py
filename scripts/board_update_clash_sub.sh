#!/bin/sh
# 更新 clash 订阅：下载新 sub.yaml，与 base.yaml 拼接并校验，通过后替换 config.yaml 并重启服务。
# 注意：订阅必须只含 proxies/proxy-groups/rules 三个顶层键（当前就是），否则与 base.yaml 拼接会产生重复键。
set -e
SUB_URL="https://sub.o2t5z.cn/clash/qflldxm8sm0jx0au"
DIR="/etc/clash"
TMP=$(mktemp)
TMP_CONFIG="$TMP.config"
trap 'rm -f "$TMP" "$TMP_CONFIG"' EXIT
curl -fsSL -A "clash.meta/v1.19.31" --max-time 60 -o "$TMP" "$SUB_URL"
cat "$DIR/base.yaml" "$TMP" > "$TMP_CONFIG"
/usr/local/bin/clash -t -d "$DIR" -f "$TMP_CONFIG" >/dev/null 2>&1
mv "$TMP_CONFIG" "$DIR/config.yaml"
systemctl restart clash
echo "subscription updated, clash restarted"
