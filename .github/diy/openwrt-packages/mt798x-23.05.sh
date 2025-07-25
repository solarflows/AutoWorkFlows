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

# D
# dnsfilter         基于dnsmasq的去广告程序
format_git_clone_output -r https://github.com/kiddin9/luci-app-dnsfilter
checkout_partial_code -r https://github.com/linkease/nas-packages-luci luci/luci-app-ddnsto
checkout_partial_code -r https://github.com/linkease/nas-packages network/services/ddnsto

checkout_partial_code -r https://github.com/openwrt/packages/ net/tailscale lang/golang

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

# Z
# ZeroTier
checkout_partial_code -r https://github.com/coolsnowwolf/packages net/zerotier
# checkout_partial_code -r https://github.com/immortalwrt/luci applications/luci-app-zerotier

exit 0
