#!/bin/bash

# 导入core
CHECK_CORE_FILE() {
    CORE_FILE="$(dirname $0)/core"
    if [[ -f "${CORE_FILE}" ]]; then
        . "${CORE_FILE}"
    else
		echo "!!! core file does not exist !!!"
        exit 1
    fi
}

CHECK_CORE_FILE

# Applications

# C
# CloudflareSpeedtest  Cloudflare Speedtest 插件
format_git_clone_output -r https://github.com/stevenjoezhang/luci-app-cloudflarespeedtest

# D
# dnsfilter         基于dnsmasq的去广告程序
format_git_clone_output -r https://github.com/kiddin9/luci-app-dnsfilter
checkout_partial_code -r https://github.com/linkease/nas-packages-luci luci/luci-app-ddnsto
checkout_partial_code -r https://github.com/linkease/nas-packages network/services/ddnsto

# L
# lucky             大吉多种功能结合体
checkout_partial_code -r https://github.com/gdy666/luci-app-lucky luci-app-lucky lucky

# M
# MosDNS            插件化可定制的DNS转发器
checkout_partial_code -r https://github.com/sbwml/luci-app-mosdns -b v5 luci-app-mosdns mosdns v2dat

# P
# PassWall1&2       科学上网
format_git_clone_output -r https://github.com/Openwrt-Passwall/openwrt-passwall-packages && mvdir openwrt-passwall-packages
checkout_partial_code -r https://github.com/Openwrt-Passwall/openwrt-passwall luci-app-passwall
checkout_partial_code -r https://github.com/Openwrt-Passwall/openwrt-passwall2 luci-app-passwall2
format_git_clone_output -r https://github.com/Zerogiven-OpenWRT-Packages/luci-app-podman

# S
# SmartDNS
format_git_clone_output -r https://github.com/pymumu/openwrt-smartdns -d smartdns
format_git_clone_output -r https://github.com/pymumu/luci-app-smartdns -b master

# T
# TaskPlan         定时任务计划管理器
checkout_partial_code -r https://github.com/sirpdboy/luci-app-taskplan luci-app-taskplan
format_git_clone_output -r https://github.com/jerrykuku/luci-theme-argon
format_git_clone_output -r https://github.com/jerrykuku/luci-app-argon-config

exit 0
