# ════════════════════════════════════════════════════════════════════════
# 签名密钥注入共享库 (R9/R12)
# 供 compile-firmware.yml / compile-packages.yml 的 Setup Signing Key 步骤
# source 引用 (infra checkout 到 AutoWorkFlows/, 先例: parse-ccache-stats.sh)。
#
# 契约 (build-artifacts.instructions.md 同步):
#   - APK: private-key.pem (ECDSA prime256v1 / RSA); IPK: usign key-build (104 字节 seckey)
#   - 输出 GITHUB_OUTPUT: sign_mode(apk|usign|random) / fingerprint
#   - random 降级兜底 = 刻意设计: 缺钥/坏钥告警 + 构建继续 (试跑/无密钥仓库不阻断);
#     REQUIRE_SIGNING=true (env 传入 inputs.require_signing) 时改硬失败,
#     阻止随机密钥/未签名产物进入 Release (emit_random_fallback)。
#   - 防泄漏: printf 写文件、chmod 600、只输出字节数/指纹不输出内容。
#
# 用法: apply_signing_key <use_apk: true|false> <keys_dir: openwrt|.>
# use_apk 探测属 executor 域知识 (seed CONFIG_USE_APK vs SDK Config-build.in),
# 留在调用方 run 块, 本库只接收结果。
# ════════════════════════════════════════════════════════════════════════

emit_random_fallback() {
  echo "sign_mode=random" >> "$GITHUB_OUTPUT"
  echo "fingerprint=none" >> "$GITHUB_OUTPUT"
  if [ "${REQUIRE_SIGNING:-false}" = "true" ]; then
    echo "::error::require_signing=true: 签名密钥缺失或无效, 拒绝继续构建"
    exit 1
  fi
  exit 0
}

apply_signing_key() {
  local use_apk="$1" keys_dir="$2"
  local APK_PRIV="${keys_dir}/private-key.pem"
  local APK_PUB="${keys_dir}/public-key.pem"
  local US_PRIV="${keys_dir}/key-build"
  local US_PUB="${keys_dir}/key-build.pub"
  local US_BIN="${keys_dir}/.seckey.bin"
  local SIGN_MODE FP KEY_BYTES KEY_B64 KEY_HEADER

  if [ "$use_apk" = "true" ]; then
    # ════════════ APK 签名 (ECDSA/RSA PEM) ════════════
    SIGN_MODE="apk"
    if [ -z "${APK_BUILD_KEY:-}" ]; then
      echo "::warning::APK_BUILD_KEY secret 未设置 — 构建系统将生成随机密钥, 设备 apk add 需 --allow-untrusted"
      emit_random_fallback
    fi
    printf '%s' "$APK_BUILD_KEY" | sed -e 's/^[[:space:]]*//' -e 's/[[:space:]]*$//' > "$APK_PRIV"
    chmod 600 "$APK_PRIV"
    sed -i 's/\r$//' "$APK_PRIV"
    echo "📏 密钥文件: $(wc -c < "$APK_PRIV") 字节 (不输出内容)"

    echo "🔍 验证密钥格式..."
    if openssl ec -in "$APK_PRIV" -check -noout 2>/dev/null; then
      echo "✅ ECDSA 私钥格式验证通过"
    elif openssl rsa -in "$APK_PRIV" -check -noout 2>/dev/null; then
      echo "::warning::APK_BUILD_KEY 是 RSA 密钥, ImmortalWrt APK 构建系统默认使用 ECDSA prime256v1"
      echo "::notice::建议重新生成 ECDSA 密钥: openssl ecparam -name prime256v1 -genkey -noout -out private-key.pem"
    else
      KEY_HEADER=$(head -c 50 "$APK_PRIV" 2>/dev/null)
      echo "::error::APK_BUILD_KEY 不是有效的 PEM 格式私钥 (需要 ECDSA prime256v1 或 RSA)"
      echo "::notice::密钥头部(仅 PEM header, 不含密钥): ${KEY_HEADER}"
      echo "::notice::本次构建将跳过签名 (产物未签名), 但构建继续"
      rm -f "$APK_PRIV"
      emit_random_fallback
    fi

    openssl ec -in "$APK_PRIV" -pubout -out "$APK_PUB" 2>/dev/null || \
      openssl rsa -in "$APK_PRIV" -pubout -out "$APK_PUB"
    chmod 644 "$APK_PUB"
    echo "✅ 公钥已派生 → ${APK_PUB}"
    FP=$(openssl sha256 < "$APK_PUB" | awk '{print $NF}')
  else
    # ════════════ IPK 签名 (usign Ed25519) ════════════
    SIGN_MODE="usign"
    # usign 私钥文件 = "untrusted comment: ..." 头 + base64(104 字节 seckey 结构)。
    # seckey 结构: pkalg[2]+kdfalg[2]+kdfrounds[4]+salt[16]+checksum[8]+fingerprint[8]+seckey[64]。
    # USIGN_KEY 存完整 key-build 文件内容, 由本地直接导入 (gh secret set USIGN_KEY < key-build)。
    if [ -z "${USIGN_KEY:-}" ]; then
      echo "::warning::USIGN_KEY secret 未设置 — 构建系统将生成随机 usign 密钥, 设备 opkg install 需 --force-checksum"
      emit_random_fallback
    fi
    printf '%s\n' "$USIGN_KEY" > "$US_PRIV"
    chmod 600 "$US_PRIV"
    sed -i 's/\r$//' "$US_PRIV"

    # 校验 seckey 结构(104 字节)并派生公钥(42 字节)+指纹。
    # 二进制经文件管道处理, 不经 bash 变量 (bash 变量无法存 NUL 字节)。
    KEY_B64=$(grep -v '^untrusted comment:' "$US_PRIV" | tr -d '\n')
    printf '%s' "$KEY_B64" | base64 -d > "$US_BIN" 2>/dev/null
    KEY_BYTES=$(wc -c < "$US_BIN")
    if [ "$KEY_BYTES" != "104" ]; then
      echo "::error::USIGN_KEY 不是有效的 usign 私钥 (seckey 结构 ${KEY_BYTES} 字节, 期望 104)"
      echo "::notice::请导入本地 key-build 文件: gh secret set USIGN_KEY --repo <repo> < key-build"
      echo "::notice::本次构建将跳过签名 (产物未签名), 但构建继续"
      rm -f "$US_PRIV" "$US_BIN"
      emit_random_fallback
    fi
    # 指纹 = seckey 结构 offset 32..40 (8 字节), 与 usign -F 输出一致。
    FP=$(dd if="$US_BIN" bs=1 skip=32 count=8 2>/dev/null | od -An -tx1 | tr -d ' \n')
    # 公钥 = "Ed" + fingerprint[8] + pubkey[32] (pubkey 在 offset 72..104), 与 usign -G 输出一致。
    {
      printf 'untrusted comment: public key %s\n' "$FP"
      { printf 'Ed'; dd if="$US_BIN" bs=1 skip=32 count=8 2>/dev/null; dd if="$US_BIN" bs=1 skip=72 count=32 2>/dev/null; } | base64 -w 0
      printf '\n'
    } > "$US_PUB"
    chmod 644 "$US_PUB"
    rm -f "$US_BIN"
    echo "📏 usign 私钥已注入 (104 字节结构, 不输出内容), 指纹 ${FP}"
  fi

  echo "sign_mode=${SIGN_MODE}" >> "$GITHUB_OUTPUT"
  echo "fingerprint=${FP}" >> "$GITHUB_OUTPUT"
  echo "🔑 ${SIGN_MODE} 签名密钥已注入 (指纹: ${FP:0:16}...)"
}
