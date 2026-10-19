# ════════════════════════════════════════════════════════════════════════
# Release 发布共享库 (R12)
# 供 compile-firmware.yml / compile-packages.yml 的 Publish/Upload release
# 步骤 source 引用 (先例: parse-ccache-stats.sh; infra checkout 到 AutoWorkFlows/)。
# 单一事实来源: 新增发布行为/安全开关只改这里, 不再在两 executor 成对接线
# (2026-10-19 泛化盘点: "两边同款"此前仅靠注释与记忆维持)。
#
# 契约 (build-artifacts.instructions.md 同步):
#   - release_type: release | prerelease | draft; edit 显式重置可纠正历史状态
#   - per-build 固件 Release 的 --target 钉构建源码 commit; 共享常驻 tag 不传
#   - 非正式 run 拒绝降级改写已转正 Release (guard_no_downgrade_formal)
#   - 资产 --clobber 覆盖 = 刻意设计 (CI 重跑幂等), 非缺陷
#
# 依赖: 调用方步骤已 export GH_TOKEN; 函数内 exit 语义 = 结束调用方整个 step
# (source 同进程, 与原 run 块内实现一致)。
# ════════════════════════════════════════════════════════════════════════

# 由 release_type 推导 CREATE_TYPE_FLAGS / EDIT_TYPE_FLAGS 两个数组。
# 非法值已由 validate-inputs 白名单拦截, 此处未知值按 release 处理。
resolve_release_type_flags() {
  CREATE_TYPE_FLAGS=()
  EDIT_TYPE_FLAGS=()
  case "${1:-release}" in
    prerelease) CREATE_TYPE_FLAGS=(--prerelease); EDIT_TYPE_FLAGS=(--prerelease --draft=false) ;;
    draft)      CREATE_TYPE_FLAGS=(--draft);      EDIT_TYPE_FLAGS=(--draft) ;;
    *)          EDIT_TYPE_FLAGS=(--draft=false --prerelease=false) ;;
  esac
}

# R8 降级防护: release_type != release 的 run 不得把已转正 (非 draft 非 prerelease)
# 的同 tag 固件 Release 降级改写; 返回 1 由调用方终止发布。
# 反向 (非正式 → release) 是有意转正, 不拦截。共享常驻 tag 刻意不加此守卫
# (其正式态是常态, tag 不含可复用 version)。
guard_no_downgrade_formal() {
  local tag="$1" repo="$2" type="$3" formal=""
  [ "$type" != "release" ] || return 0
  formal=$(gh release view "$tag" --repo "$repo" \
    --json draft,prerelease --jq 'select(.draft == false and .prerelease == false) | "formal"' 2>/dev/null) || true
  if [ "$formal" = "formal" ]; then
    echo "::error::tag ${tag} 已存在正式 Release, 拒绝以 ${type} 类型覆盖 (换 version/tag 重试, 或确需降级请手动处理该 Release)"
    return 1
  fi
}

# R2 逐文件上传 + 3 次退避重试 (GitHub API/存储端 500/502/超时抖动)。
# 用法: upload_asset_retry <tag> <repo> <file...>
upload_asset_retry() {
  local tag="$1" repo="$2"
  shift 2
  local uploaded=false
  local attempt
  for attempt in 1 2 3; do
    if gh release upload "$tag" --repo "$repo" "$@" --clobber; then
      uploaded=true
      break
    fi
    echo "⚠️ 资产上传失败 [尝试 ${attempt}/3]: $*，等待 $((attempt * 5)) 秒后重试..."
    sleep $((attempt * 5))
  done
  if [ "$uploaded" != "true" ]; then
    echo "::error::资产上传失败，已达最大重试次数: $*"
    return 1
  fi
}

# G14/R10 同包多版本收敛: 每个包名按 updated_at 保留最近 <keep> 版 (含 .sha256)。
# 版本号变化 → 文件名不同 → --clobber 不会覆盖, 只会无限累积
# (packages-ipq807x 曾出现 luci-app-passwall 3 版共存)。公钥 (.pem/.pub) 与
# 解析失败的文件永不清; 清理失败只告警不阻塞发布 (写入方自约束, 与 artifacts
# keep_versions 同模式; keep 下限 1 = 有界保留是收敛的立项前提, 不提供禁用档)。
# 用法: purge_pkg_versions <tag> <repo> <keep>
purge_pkg_versions() {
  local tag="$1" repo="$2" keep="$3"
  if ! gh release view "$tag" --repo "$repo" --json assets \
    --jq '[.assets[] | select(.name | test("\\.(apk|ipk)$"))]' > /tmp/pkg_assets.json 2>/dev/null; then
    echo "::warning::软件包资产列表获取失败, 跳过版本收敛"
    return 0
  fi
  if [ ! -s /tmp/pkg_assets.json ] || [ "$(jq 'length' /tmp/pkg_assets.json)" -eq 0 ]; then
    echo "ℹ️ 软件包版本收敛: 无需清理 (无 apk/ipk 资产)"
    return 0
  fi
  # 包名提取: apk "pkg-1.2.3-r1.apk" → pkg (去最后两段 ver-rN);
  # ipk "pkg_1.2.3-1_arch.ipk" → pkg (去 _ver-rev_arch 段)。
  # 提取失败 (无版本结构) 归 default 组, 永不清。
  jq -r 'sort_by(.updated_at) | reverse
         | group_by(.name | sub("-[^-]+-r[0-9]+\\.apk$";"") | sub("_[^_]+-[^-]+_[^.]+\\.ipk$";"") | if . == "" then "default" else . end)
         | .[] | .[ $KEEP : ][] | .name' \
    --argjson KEEP "$keep" /tmp/pkg_assets.json > /tmp/pkg_purge.txt || : > /tmp/pkg_purge.txt
  if [ ! -s /tmp/pkg_purge.txt ]; then
    echo "ℹ️ 软件包版本收敛: 无需清理 (每包 ≤ ${keep} 版)"
    return 0
  fi
  echo "ℹ️ 软件包版本收敛: 以下 $(wc -l < /tmp/pkg_purge.txt) 个旧版本将被清理 (每包保留 ${keep} 版)"
  cat /tmp/pkg_purge.txt
  local old
  while IFS= read -r old; do
    [ -n "$old" ] || continue
    gh release delete-asset "$tag" "$old" --repo "$repo" --yes 2>/dev/null \
      || echo "::warning::清理 $old 失败 (保留, 下轮重试)"
    # 配套 .sha256 同步清理 (存在才清)。
    # 注意: gh --jq 不支持 --arg (本仓库已记录坑, 旧实现在此处误用 → 表达式
    # 报错被 if 吞掉, sha256 伴生清理静默失效)。文件名白名单 [A-Za-z0-9+._-]
    # 无引号/反斜杠, 内嵌双引号表达式安全 (与 unified run list 查询同模式)。
    if gh release view "$tag" --repo "$repo" --json assets \
      --jq "[.assets[].name] | index(\"${old}.sha256\") != null" | grep -qx true; then
      gh release delete-asset "$tag" "${old}.sha256" --repo "$repo" --yes 2>/dev/null || true
    fi
  done < /tmp/pkg_purge.txt
}
