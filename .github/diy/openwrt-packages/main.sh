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

format_git_clone_output -r https://github.com/hyy-666/my-diy -b main && mvdir my-diy

# LuCI Theme

format_git_clone_output -r https://github.com/Leo-Jo-My/luci-theme-argon-dark-mod
format_git_clone_output -r https://github.com/hyy-666/luci-theme-Butterfly-dark
format_git_clone_output -r https://github.com/apollo-ng/luci-theme-darkmatter
format_git_clone_output -r https://github.com/jerrykuku/luci-theme-argon -b 18.06
format_git_clone_output -r https://github.com/thinktip/luci-theme-neobird
format_git_clone_output -r https://github.com/derisamedia/luci-theme-alpha
# checkout_partial_code -r https://github.com/lynxnexy/packages luci-theme-tano #missing
# svn co https://github.com/Carseason/openwrt-themedog/trunk/luci/luci-themedog luci-theme-dog
# svn co https://github.com/koshev-msk/modemfeed/trunk/luci/themes && mvdir themes
# format_git_clone_output -r https://github.com/kiddin9/luci-theme-edge
# format_git_clone_output -r https://github.com/kenzok78/luci-theme-argonne
# svn co https://github.com/liuran001/openwrt-theme/trunk/luci-theme-argon-lr
# svn co https://github.com/kenzok8/litte/trunk/luci-theme-argon_new
# svn co https://github.com/kenzok8/litte/trunk/luci-theme-opentopd_new
# svn co https://github.com/kenzok8/litte/trunk/luci-theme-atmaterial_new
# svn co https://github.com/kenzok8/litte/trunk/luci-theme-mcat
# svn co https://github.com/kenzok8/litte/trunk/luci-theme-tomato
format_git_clone_output -r https://github.com/jerrykuku/luci-app-argon-config -b 18.06

# Applications

# A
# 阿里网盘Webdav挂载
checkout_partial_code -r https://github.com/messense/aliyundrive-webdav openwrt/aliyundrive-webdav openwrt/luci-app-aliyundrive-webdav
# advanced          配置文件级别的设置修改插件
format_git_clone_output -r https://github.com/sirpdboy/luci-app-advanced
# airconnect        将DLNA设备转为AirPlay设备
checkout_partial_code -r https://github.com/sbwml/luci-app-airconnect luci-app-airconnect airconnect
# amlogic           固件更新功能加强
checkout_partial_code -r https://github.com/ophub/luci-app-amlogic luci-app-amlogic
# autoipsetadder    自动添加不能访问的网站到gfwlist转发链
format_git_clone_output -r https://github.com/rufengsuixing/luci-app-autoipsetadder
# autotimeset       设置OpenWRT按时执行某个操作
format_git_clone_output -r https://github.com/sirpdboy/luci-app-autotimeset
# autorepeater      OpenWRT自动中继网络
format_git_clone_output -r https://github.com/peter-tank/luci-app-autorepeater

# B
# beardropper       控制dropbear的登录
format_git_clone_output -r https://github.com/NateLol/luci-app-beardropper

# C
# cdnspeedtest                  CloudFlare CDN 测速
checkout_partial_code -r https://github.com/immortalwrt/packages net/cdnspeedtest
checkout_partial_code -r https://github.com/mingxiaoyu/luci-app-cloudflarespeedtest applications/luci-app-cloudflarespeedtest
# control-guest-wifi            访客wifi
checkout_partial_code -r https://github.com/zxlhhyccc/bf-package-master zxlhhyccc/luci-app-control-guest-wifi

# D
# dnsfilter         基于dnsmasq的去广告程序
format_git_clone_output -r https://github.com/kiddin9/luci-app-dnsfilter
# dockerman         Docker管理界面
checkout_partial_code -r https://github.com/lisaac/luci-app-dockerman applications/luci-app-dockerman

# F
# filebrowser       文件管理器
checkout_partial_code -r https://github.com/immortalwrt/packages/ utils/filebrowser
checkout_partial_code -r https://github.com/immortalwrt/luci/ -b openwrt-18.06 applications/luci-app-filebrowser

# H
# homebridge        米家的智能家居到Apple HomeKit的桥接
format_git_clone_output -r https://github.com/shanglanxin/luci-app-homebridge
# HomeProxy         Tianling Shen主导的FQ
format_git_clone_output -r https://github.com/immortalwrt/homeproxy
# Hyy2001X          软件库
checkout_partial_code -r https://github.com/Hyy2001X/AutoBuild-Packages.git luci-app-adguardhome luci-app-natter luci-app-onliner luci-app-webd webd natter

# I
# ikoolproxy        广告过滤
format_git_clone_output -r https://github.com/1wrt/luci-app-ikoolproxy.git && mv luci-app-ikoolproxy/koolproxy ./
# iperf             测速软件的luci界面
checkout_partial_code -r https://github.com/Ysurac/openmptcprouter-feeds luci-app-iperf
# iptvhelper        融合IPTV到家庭局域网
format_git_clone_output -r https://github.com/riverscn/openwrt-iptvhelper && mvdir openwrt-iptvhelper
# irqbalance        修复lean的irqbalance
checkout_partial_code -r https://github.com/openwrt/packages utils/irqbalance

# L
# libtorrent-rasterbar
checkout_partial_code -r https://github.com/immortalwrt/packages libs/libtorrent-rasterbar
# linkease          易有云官方软件(易有云ddnsto,linkshare)
checkout_partial_code -r https://github.com/linkease/istore/ luci/*
checkout_partial_code -r https://github.com/linkease/nas-packages-luci luci/*
checkout_partial_code -r https://github.com/linkease/istore-ui app-store-ui
checkout_partial_code -r https://github.com/linkease/nas-packages network/services/* multimedia/*
# lucky             大吉多种功能结合体
checkout_partial_code -r https://github.com/gdy666/luci-app-lucky luci-app-lucky lucky

# M
# # MosDNS            插件化可定制的DNS转发器
# svn co https://github.com/QiuSimons/openwrt-mos/trunk/luci-app-mosdns
# svn co https://github.com/QiuSimons/openwrt-mos/trunk/mosdns
checkout_partial_code -r https://github.com/sbwml/luci-app-mosdns -b v5 luci-app-mosdns mosdns v2dat
# mmconfig          3G/LTE 解调器设置
format_git_clone_output -r https://github.com/erdoukki/luci-app-mmconfig
# modeminfo         3G/LTE 解调器信息
format_git_clone_output -r https://github.com/4IceG/luci-app-modeminfo
# msd_lite          新一代IPTV转发
format_git_clone_output -r https://github.com/ximiTech/luci-app-msd_lite
format_git_clone_output -r https://github.com/ximiTech/msd_lite

# N
# nezha             开源、轻量的服务器和网站监控、运维工具
checkout_partial_code -r https://github.com/Erope/openwrt_nezha luci-app-nezha openwrt-nezha && mv openwrt-nezha nezha-agent
# netdata
format_git_clone_output -r https://github.com/sirpdboy/luci-app-netdata
# netspeedtest      网络测速
format_git_clone_output -r https://github.com/sirpdboy/netspeedtest && mvdir netspeedtest
# nft-qos           基于nftables的qos工具(静态、动态双模式)
checkout_partial_code -r https://github.com/x-wrt/packages net/nft-qos
checkout_partial_code -r https://github.com/x-wrt/luci applications/luci-app-nft-qos
# ngrokc            c语言实现的ngrok
checkout_partial_code -r https://github.com/immortalwrt/packages net/ngrokc
# nodogsplash       无WIFIDOG实现WIFI认证
format_git_clone_output -r https://github.com/tty228/luci-app-nodogsplash

# O
# OpenAppFilter     内核级应用过滤
format_git_clone_output -r https://github.com/destan19/OpenAppFilter && mvdir OpenAppFilter
# openclash         OpenWRT的Clash
checkout_partial_code -r https://github.com/vernesong/OpenClash luci-app-openclash

# P
# PassWall1&2       科学上网
format_git_clone_output -r https://github.com/xiaorouji/openwrt-passwall-packages && mvdir openwrt-passwall-packages
checkout_partial_code -r https://github.com/xiaorouji/openwrt-passwall luci-app-passwall
checkout_partial_code -r https://github.com/xiaorouji/openwrt-passwall2 luci-app-passwall2
# # pingcontrol       网络重连
# svn co https://github.com/koshev-msk/modemfeed/trunk/luci/applications/luci-app-pingcontrol
# svn co https://github.com/koshev-msk/modemfeed/trunk/packages/net/pingcontrol
# pikpak-webdav     海外迅雷网盘
checkout_partial_code -r https://github.com/ykxVK8yL5L/pikpak-webdav/ openwrt/*
# poweroff          关机插件
format_git_clone_output -r https://github.com/esirplayground/luci-app-poweroff
# pushbot           全能推送
format_git_clone_output -r https://github.com/zzsj0928/luci-app-pushbot

# R
# rtorrent          OpenWRT的rTorrent客户端
format_git_clone_output -r https://github.com/wolandmaster/luci-app-rtorrent

# S
# SmartDNS          DNS解析工具
format_git_clone_output -r https://github.com/pymumu/luci-app-smartdns -b lede
checkout_partial_code -r https://github.com/immortalwrt/packages net/smartdns
# smartinfo         S.M.A.R.T监控软件
format_git_clone_output -r https://github.com/huajijam/luci-app-smartinfo
# sms-tool          sms-tool的luci界面
checkout_partial_code -r https://github.com/4IceG/luci-app-sms-tool luci-app-sms-tool sms-tool
# ssr-plus          科学上网
checkout_partial_code -r https://github.com/fw876/helloworld luci-app-ssr-plus lua-neturl redsocks2 shadow-tls
# subconverter      订阅转换
format_git_clone_output -r https://github.com/WYC-2020/openwrt-subconverter && mvdir openwrt-subconverter
# sundaqiang        sundaqiang编写的软件合集(luci-app-nginx-manager,luci-app-supervisord,luci-app-wolplus)
checkout_partial_code -r https://github.com/sundaqiang/openwrt-packages luci-app-nginx-manager luci-app-supervisord luci-app-wolplus
# syncthing         文件同步
checkout_partial_code -r https://github.com/immortalwrt/luci -b openwrt-18.06 applications/luci-app-syncthing

# T
# tasks             定时任务
checkout_partial_code -r https://github.com/jjm2473/openwrt-apps luci-app-tasks
# luci-app-tailscaler 异地组网
checkout_partial_code -r https://github.com/zijieKwok/luci-app-tailscale1 luci-app-tailscaler
# tencentcloud_ddns 腾讯云DDNS
checkout_partial_code -r https://github.com/Tencent-Cloud-Plugins/tencentcloud-openwrt-plugin-ddns tencentcloud_ddns && mv tencentcloud_ddns luci-app-tencentddns
# tcpdump           抓包工具
format_git_clone_output -r https://github.com/KFERMercer/luci-app-tcpdump
# tinyfilemanager   最小web-based文件管理工具
format_git_clone_output -r https://github.com/muink/luci-app-tinyfilemanager

# W
# wifidog           WIFIDOG的luci管理界面WIFI认证
format_git_clone_output -r https://github.com/walkingsky/luci-wifidog && mv luci-wifidog luci-app-wifidog

# X
# xmurp-ua          在 OpenWrt 上修改 HTTP 流量的 UA
format_git_clone_output -r https://github.com/CHN-beta/xmurp-ua

exit 0
