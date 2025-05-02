#!/bin/bash


# 执行 git clone 命令，并将输出重定向到指定文件
format_git_clone_output() {
  local repo_url=""
  local branch=""
  local output_file=$(mktemp)

  # 解析命名参数
  while [[ $# -gt 0 ]]; do
    case "$1" in
      -r | --repo )
        repo_url="$2"
        shift 2
        ;;
      -b | --branch )
        branch="$2"
        shift 2
        ;;
      * )
        echo "未知选项: $1"
        exit 1
        ;;
    esac
  done

  if [[ -z $repo_url ]]; then
    echo "必须提供 -r 或 --repo 参数"
    exit 1
  fi

  # 进入当前目录，并执行 git clone 命令，将输出重定向到临时文件
  if ! (git clone --depth 1 --quiet ${branch:+--branch "$branch"} "$repo_url" > "$output_file" 2>&1); then
    cat "$output_file"  # 输出日志信息
    rm "$output_file"   # 删除临时文件
    echo "Git clone $repo_url 出错，请查看日志信息。"
    exit 1  # 退出脚本并返回错误状态码
  fi

  # 输出成功信息
  echo "克隆成功：$repo_url"

  rm "$output_file"  # 删除临时文件

  rm -rf ./*/.git
  rm -f ./*/.gitattributes
  rm -rf ./*/.svn
  rm -rf ./*/.github
  rm -rf ./*/.gitignore
}

# 使用git检出指定的代码到目标运行目录或当前目录
checkout_partial_code() {
  local repo_url=""
  local branch=""


  # 解析命令行参数
  while [[ $# -gt 0 ]]; do
    case "$1" in
      -r | --repo)
        repo_url=$2
        shift 2
        ;;
      -b | --branch)
        branch=$2
        shift 2
        ;;
      *)
        break
        ;;
    esac
  done

  # 检查必需参数
  if [ -z "$repo_url" ]; then
    echo "错误：缺少必需的参数：-r | --repo <repository_url>"
    exit 1
  fi

  # 克隆GitHub仓库到临时目录并切换到指定分支（如果提供了分支参数），失败时报错并退出
  local temp_dir=$(mktemp -d)
  if ! git clone --depth 1 --quiet ${branch:+--branch "$branch"} "$repo_url" "$temp_dir"; then
    echo "检出出错：$repo_url"
    rm -rf "$temp_dir"
    exit 1
  fi

  # 提取指定子目录到目标运行目录或当前目录，若文件夹不存在则报错并退出
  for dir in "${@}"; do
    if [ "$dir" != "--repo" ] && [ "$dir" != "-r" ] && [ "$dir" != "--branch" ] && [ "$dir" != "-b" ]; then
        if ! cp -r $temp_dir/$dir .;then
          echo "错误：$dir 文件夹不存在于仓库中"
          exit 1
        fi
    fi
  done

  # 删除临时目录
  rm -rf "$temp_dir"

  echo "检出成功：$repo_url"
}

function mvdir() {
    if [ -d "$1" ]; then
        find "$1" -mindepth 1 -maxdepth 1 -type d -exec mv -t ./ {} +
        rm -rf "$1"
    else
        echo "目录 $1 不存在"
    fi
}

# Applications

# D
# dnsfilter         基于dnsmasq的去广告程序
format_git_clone_output -r https://github.com/kiddin9/luci-app-dnsfilter
checkout_partial_code -r https://github.com/linkease/nas-packages-luci luci/luci-app-ddnsto
checkout_partial_code -r https://github.com/linkease/nas-packages network/services/ddnsto

checkout_partial_code -r https://github.com/openwrt/packages/ net/tailscale lang/golang
checkout_partial_code -r https://github.com/padavanonly/immortalwrt-mt798x-24.10 package/mtk/applications/luci-app-mwan3helper-chinaroute package/mtk/applications/luci-app-upnp-mtk-adjust package/mtk/applications/luci-app-wrtbwmon package/mtk/applications/miniupnpd-mtk-adjust package/mtk/applications/wrtbwmon

# L
# lucky             大吉多种功能结合体
checkout_partial_code -r https://github.com/gdy666/luci-app-lucky luci-app-lucky lucky

# M
# MosDNS            插件化可定制的DNS转发器
checkout_partial_code -r https://github.com/sbwml/luci-app-mosdns -b v5 luci-app-mosdns mosdns v2dat

# P
# PassWall1&2       科学上网
format_git_clone_output -r https://github.com/xiaorouji/openwrt-passwall-packages && mvdir openwrt-passwall-packages
checkout_partial_code -r https://github.com/xiaorouji/openwrt-passwall luci-app-passwall
checkout_partial_code -r https://github.com/xiaorouji/openwrt-passwall2 luci-app-passwall2

# S
# SmartDNS
checkout_partial_code -r https://github.com/immortalwrt/packages net/smartdns
format_git_clone_output -r https://github.com/pymumu/luci-app-smartdns -b master

# T
# TaskPlan         定时任务计划管理器
checkout_partial_code -r https://github.com/sirpdboy/luci-app-taskplan luci-app-taskplan
format_git_clone_output -r https://github.com/jerrykuku/luci-theme-argon
format_git_clone_output -r https://github.com/jerrykuku/luci-app-argon-config

# Z
# ZeroTier
checkout_partial_code -r https://github.com/coolsnowwolf/packages net/zerotier
checkout_partial_code -r https://github.com/immortalwrt/luci applications/luci-app-zerotier

exit 0
