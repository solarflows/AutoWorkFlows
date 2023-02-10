#!/bin/bash
function git_sparse_clone() {
    branch="$1" rurl="$2" localdir="$3" && shift 3
    git clone -b $branch --depth 1 --filter=blob:none --sparse $rurl $localdir
    cd $localdir
    git sparse-checkout init --cone
    git sparse-checkout set $@
    mv -n $@ ../
    cd ..
    rm -rf $localdir
}

function mvdir() {
    mv -f $(find $1/* -maxdepth 0 -type d) ./
    rm -rf $1
}

git clone --depth 1 https://github.com/hyy-666/my-diy -b "$1" && mvdir my-diy

# LuCI Theme

git clone --depth 1 https://github.com/Leo-Jo-My/luci-theme-argon-dark-mod
git clone --depth 1 https://github.com/hyy-666/luci-theme-Butterfly-dark
git clone --depth 1 https://github.com/apollo-ng/luci-theme-darkmatter
git clone --depth 1 https://github.com/jerrykuku/luci-theme-argon -b 18.06
git clone --depth 1 https://github.com/thinktip/luci-theme-neobird
git clone --depth 1 https://github.com/lynxnexy/luci-theme-tano
svn co https://github.com/Carseason/openwrt-themedog/trunk/luci/luci-themedog luci-theme-dog
svn co https://github.com/koshev-msk/modemfeed/trunk/luci/themes mvdir themes
# git clone --depth 1 https://github.com/kiddin9/luci-theme-edge
# git clone --depth 1 https://github.com/kenzok78/luci-theme-argonne
# svn co https://github.com/liuran001/openwrt-theme/trunk/luci-theme-argon-lr
# svn co https://github.com/kenzok8/litte/trunk/luci-theme-argon_new
# svn co https://github.com/kenzok8/litte/trunk/luci-theme-opentopd_new
# svn co https://github.com/kenzok8/litte/trunk/luci-theme-atmaterial_new
# svn co https://github.com/kenzok8/litte/trunk/luci-theme-mcat
# svn co https://github.com/kenzok8/litte/trunk/luci-theme-tomato
git clone --depth 1 https://github.com/jerrykuku/luci-app-argon-config

# Applications

# A
# 阿里网盘Webdav挂载
svn co https://github.com/messense/aliyundrive-webdav/trunk/openwrt aliyundrive && mvdir aliyundrive
# AdguardHome广告过滤
svn co https://github.com/kenzok8/jell/trunk/luci-app-adguardhome
svn co https://github.com/kenzok8/jell/trunk/adguardhome
# advanced          配置文件级别的设置修改插件
git clone --depth 1 https://github.com/sirpdboy/luci-app-advanced
# autoipsetadder    自动添加不能访问的网站到gfwlist转发链
git clone --depth 1 https://github.com/rufengsuixing/luci-app-autoipsetadder
# autotimeset       设置OpenWRT按时执行某个操作
git clone --depth 1 https://github.com/sirpdboy/luci-app-autotimeset
# autorepeater      OpenWRT自动中继网络
git clone --depth 1 https://github.com/peter-tank/luci-app-autorepeater
# amule             电驴 from lean
svn co https://github.com/coolsnowwolf/luci/trunk/applications/luci-app-amule
svn co https://github.com/coolsnowwolf/packages/trunk/net/amule
svn co https://github.com/coolsnowwolf/packages/trunk/net/antileech

# B
# beardropper       控制dropbear的登录
git clone --depth 1 https://github.com/NateLol/luci-app-beardropper

# C
# cdnspeedtest      CloudFlare CDN 测速
svn co https://github.com/immortalwrt/packages/trunk/net/cdnspeedtest
svn co https://github.com/mingxiaoyu/luci-app-cloudflarespeedtest/trunk/applications/luci-app-cloudflarespeedtest
# control-weburl    网址访问控制
git clone --depth 1 https://github.com/gdck/luci-app-control-weburl
# control-speedlimit联网控制
svn co https://github.com/sirpdboy/sirpdboy-package/trunk/luci-app-control-speedlimit

# D
# dnsfilter         基于dnsmasq的去广告程序
git clone --depth 1 https://github.com/kiddin9/luci-app-dnsfilter
# dockerman         Docker管理界面
svn co https://github.com/lisaac/luci-app-dockerman/trunk/applications/luci-app-dockerman

# E
# easymesh          基于batman wpad-mesh dawn 的wlan漫游实现
git clone --depth 1 https://github.com/ntlf9t/luci-app-easymesh

# F
# filebrowser       文件管理器
git clone --depth 1 https://github.com/immortalwrt/openwrt-filebrowser && mvdir openwrt-filebrowser

# H
# homebridge        米家的智能家居到Apple HomeKit的桥接
git clone --depth 1 https://github.com/shanglanxin/luci-app-homebridge

# I
# ikoolproxy        广告过滤
git clone --depth 1 https://github.com/1wrt/luci-app-ikoolproxy.git && mv luci-app-ikoolproxy/koolproxy ./
# iperf             测速软件的luci界面
svn co https://github.com/Ysurac/openmptcprouter-feeds/trunk/luci-app-iperf
# iptvhelper        融合IPTV到家庭局域网
git clone --depth 1 https://github.com/riverscn/openwrt-iptvhelper && mvdir openwrt-iptvhelper
# irqbalance        修复lean的irqbalance
svn co https://github.com/openwrt/packages/trunk/utils/irqbalance
svn co https://github.com/QiuSimons/OpenWrt-Add/trunk/luci-app-irqbalance

# L
# linkease          易有云官方软件(易有云ddnsto,linkshare)
svn co https://github.com/linkease/istore/trunk/luci && mvdir luci
svn co https://github.com/linkease/nas-packages-luci/trunk/luci && mvdir luci
svn co https://github.com/linkease/istore-ui/trunk/app-store-ui
svn co https://github.com/linkease/nas-packages/trunk/network/services && mvdir services
svn co https://github.com/linkease/nas-packages/trunk/multimedia && mvdir multimedia
# lucky             大吉多种功能结合体
git clone --depth 1 https://github.com/sirpdboy/luci-app-lucky && mvdir luci-app-lucky
# log 美化显示log
git clone --depth 1 https://github.com/hyy-666/luci-app-log

# M
# mbedtls           修复mbedtls Armv8ce 支持
svn co https://github.com/immortalwrt/immortalwrt/trunk/package/libs/mbedtls
# MosDNS            插件化可定制的DNS转发器
svn co https://github.com/QiuSimons/openwrt-mos/trunk/luci-app-mosdns
svn co https://github.com/QiuSimons/openwrt-mos/trunk/mosdns
# mmconfig          3G/LTE 解调器设置
git clone --depth 1 https://github.com/erdoukki/luci-app-mmconfig
# modeminfo         3G/LTE 解调器信息
git clone --depth 1 https://github.com/4IceG/luci-app-modeminfo
# msd_lite          新一代IPTV转发
git clone --depth 1 https://github.com/ximiTech/luci-app-msd_lite
git clone --depth 1 https://github.com/ximiTech/msd_lite

# N
# nezha             开源、轻量的服务器和网站监控、运维工具
git clone --depth 1 https://github.com/Erope/openwrt_nezha && mvdir openwrt_nezha
# netspeedtest      网络测速
git clone --depth 1 https://github.com/sirpdboy/netspeedtest && mvdir netspeedtest
# nft-qos           基于nftables的qos工具(静态、动态双模式)
svn co https://github.com/x-wrt/packages/trunk/net/nft-qos
svn co https://github.com/x-wrt/luci/trunk/applications/luci-app-nft-qos
# ngrokc            c语言实现的ngrok
svn co https://github.com/immortalwrt/packages/trunk/net/ngrokc
# nodogsplash       无WIFIDOG实现WIFI认证
git clone --depth 1 https://github.com/tty228/luci-app-nodogsplash

# O
# onliner           在线人数统计
git clone --depth 1 https://github.com/selfcan/luci-app-onliner
# OpenAppFilter     内核级应用过滤
git clone --depth 1 https://github.com/destan19/OpenAppFilter && mvdir OpenAppFilter
# openclash         OpenWRT的Clash
svn co https://github.com/vernesong/OpenClash/trunk/luci-app-openclash

# P
# PassWall1&2       科学上网
git clone --depth 1 https://github.com/xiaorouji/openwrt-passwall -b packages packages && mvdir packages
git clone --depth 1 https://github.com/xiaorouji/openwrt-passwall -b luci openwrt-passwall && mvdir openwrt-passwall
git clone --depth 1 https://github.com/xiaorouji/openwrt-passwall2 && mvdir openwrt-passwall2
# pingcontrol       网络重连
svn co https://github.com/kenzok8/jell/trunk/luci-app-pingcontrol
# pikpak-webdav     海外迅雷网盘
svn co https://github.com/ykxVK8yL5L/pikpak-webdav/tree/main/openwrt && mvdir openwrt
# poweroff          关机插件
git clone --depth 1 https://github.com/esirplayground/luci-app-poweroff
# pushbot           全能推送
git clone --depth 1 https://github.com/zzsj0928/luci-app-pushbot

# R
# rtorrent          OpenWRT的rTorrent客户端
git clone --depth 1 https://github.com/wolandmaster/luci-app-rtorrent

# S
# SmartDNS          DNS解析工具
git clone -b lede https://github.com/pymumu/luci-app-smartdns
svn co https://github.com/immortalwrt/packages/trunk/net/smartdns
# smartinfo         S.M.A.R.T监控软件
svn co https://github.com/KFERMercer/OpenWrt/trunk/package/kferm/luci-app-smartinfo
# sms-tool          sms-tool的luci界面
git clone --depth 1 https://github.com/4IceG/luci-app-sms-tool smstool && mvdir smstool
# ssr-plus          科学上网
svn co https://github.com/fw876/helloworld/trunk/luci-app-ssr-plus
# subconverter      订阅转换
git clone --depth 1 https://github.com/WYC-2020/openwrt-subconverter && mvdir openwrt-subconverter
# sundaqiang        sundaqiang编写的软件合集(luci-app-nginx-manager,luci-app-supervisord,luci-app-wolplus)
git clone --depth 1 https://github.com/sundaqiang/openwrt-packages && mv -n openwrt-packages/luci-app-{nginx-manager,supervisord,wolplus} ./
rm -rf openwrt-packages
# syncthing         文件同步
svn co https://github.com/immortalwrt/luci/branches/openwrt-18.06-k5.4/applications/luci-app-syncthing

# T
# tasks             定时任务
svn co https://github.com/jjm2473/openwrt-apps/trunk/luci-app-tasks
# tencentcloud_ddns 腾讯云DDNS
svn co https://github.com/Tencent-Cloud-Plugins/tencentcloud-openwrt-plugin-ddns/trunk/tencentcloud_ddns luci-app-tencentddns
# tcpdump           抓包工具
git clone --depth 1 https://github.com/KFERMercer/luci-app-tcpdump

# W
# wifidog           WIFIDOG的luci管理界面WIFI认证
git clone --depth 1 https://github.com/walkingsky/luci-wifidog luci-app-wifidog

# X
# xmurp-ua          在 OpenWrt 上修改 HTTP 流量的 UA
git clone --depth 1 https://github.com/CHN-beta/xmurp-ua

rm -rf ./*/.git
rm -f ./*/.gitattributes
rm -rf ./*/.svn
rm -rf ./*/.github
rm -rf ./*/.gitignore
exit 0
