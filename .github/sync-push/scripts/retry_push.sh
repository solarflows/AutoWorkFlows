#!/usr/bin/env bash
# retry_push.sh
# 跨 Job 通用推送函数：使用远端当前 SHA 建立显式 lease，避免无条件覆盖分支；
# 比对内容树跳过空提交；支持重试与指数退避。
#
# 用法: retry_push <remote_url_or_name> <refspec> [max_retries] [retry_delay]
# 示例: retry_push "https://github.com/solarflows/lede.git" "HEAD:refs/heads/$target"

retry_push() {
  local remote_url="$1"
  local refspec="$2"
  local max_retries="${3:-3}"
  local retry_delay="${4:-10}"
  local branch="${refspec#HEAD:refs/heads/}"
  local remote_sha expected lease current

  case "$refspec" in
    HEAD:refs/heads/*) ;;
    *) echo "::error::无效的目标 refspec: $refspec"; return 2 ;;
  esac

  if ! remote_sha=$(git ls-remote "$remote_url" "refs/heads/$branch"); then
    echo "::error::读取远端分支失败: $remote_url refs/heads/$branch"
    return 1
  fi

  expected=$(printf '%s\n' "$remote_sha" | awk 'NR == 1 { print $1 }')

  if [ -n "$expected" ]; then
    # 若远端已有该分支，检查其内容树是否与本地 HEAD 完全一致
    # 若文件树一致（代码内容零差异），跳过推送以避免产生无意义的空提交，防止下游工作流误判变更
    if git fetch --no-tags --depth=1 "$remote_url" "refs/heads/$branch" 2>/dev/null; then
      local remote_tree local_tree
      remote_tree=$(git rev-parse "FETCH_HEAD^{tree}" 2>/dev/null || true)
      local_tree=$(git rev-parse "HEAD^{tree}" 2>/dev/null || true)
      if [ -n "$remote_tree" ] && [ "$remote_tree" = "$local_tree" ]; then
        echo "🟢 远端分支 $branch 内容树与本地完全一致 (${local_tree:0:7})，跳过推送"
        return 0
      fi
    fi
    lease="--force-with-lease=refs/heads/$branch:$expected"
  else
    lease="--force-with-lease=refs/heads/$branch:"
  fi

  for i in $(seq 1 "$max_retries"); do
    if git push "$remote_url" "$lease" "$refspec" 2>&1; then
      return 0
    fi
    if ! remote_sha=$(git ls-remote "$remote_url" "refs/heads/$branch"); then
      echo "::error::读取远端分支失败: $remote_url refs/heads/$branch"
      return 1
    fi
    current=$(printf '%s\n' "$remote_sha" | awk 'NR == 1 { print $1 }')
    if [ "$current" = "$(git rev-parse HEAD)" ]; then
      echo "✅ 远端已包含本地 HEAD"
      return 0
    fi
    if [ "$current" != "$expected" ]; then
      echo "::error::远端分支已在重试期间变化，拒绝覆盖: refs/heads/$branch"
      return 1
    fi
    if [ "$i" -lt "$max_retries" ]; then
      echo "::warning::推送失败，${retry_delay}秒后重试 ($i/$max_retries)..."
      sleep "$retry_delay"
      retry_delay=$((retry_delay * 2))
    fi
  done

  echo "::error::达到最大重试次数 ($max_retries)，推送失败: $remote_url $refspec"
  return 1
}
