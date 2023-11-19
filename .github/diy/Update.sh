#!/bin/bash


function git_sparse_clone() {
    rurl="$1" branch="$2" localdir="temp_sparse_clone_dir" && shift 2
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
# svn co https://github.com/Carseason/openwrt-themedog/trunk/luci/luci-themedog luci-theme-dog
# svn co https://github.com/koshev-msk/modemfeed/trunk/luci/themes && mvdir themes
# git clone --depth 1 https://github.com/kiddin9/luci-theme-edge
# git clone --depth 1 https://github.com/kenzok78/luci-theme-argonne
# svn co https://github.com/liuran001/openwrt-theme/trunk/luci-theme-argon-lr
# svn co https://github.com/kenzok8/litte/trunk/luci-theme-argon_new
# svn co https://github.com/kenzok8/litte/trunk/luci-theme-opentopd_new
# svn co https://github.com/kenzok8/litte/trunk/luci-theme-atmaterial_new
# svn co https://github.com/kenzok8/litte/trunk/luci-theme-mcat
# svn co https://github.com/kenzok8/litte/trunk/luci-theme-tomato
git clone --depth 1 https://github.com/jerrykuku/luci-app-argon-config -b 18.06

# Applications

# A
# 阿里网盘Webdav挂载
svn co https://github.com/messense/aliyundrive-webdav/trunk/openwrt aliyundrive && mvdir aliyundrive
# advanced          配置文件级别的设置修改插件
git clone --depth 1 https://github.com/sirpdboy/luci-app-advanced
# autoipsetadder    自动添加不能访问的网站到gfwlist转发链
git clone --depth 1 https://github.com/rufengsuixing/luci-app-autoipsetadder
# autotimeset       设置OpenWRT按时执行某个操作
git clone --depth 1 https://github.com/sirpdboy/luci-app-autotimeset
# autorepeater      OpenWRT自动中继网络
git clone --depth 1 https://github.com/peter-tank/luci-app-autorepeater

# B
# beardropper       控制dropbear的登录
git clone --depth 1 https://github.com/NateLol/luci-app-beardropper

# C
# cdnspeedtest                  CloudFlare CDN 测速
svn co https://github.com/immortalwrt/packages/trunk/net/cdnspeedtest
svn co https://github.com/mingxiaoyu/luci-app-cloudflarespeedtest/trunk/applications/luci-app-cloudflarespeedtest
# control-guest-wifi            访客wifi
svn co https://github.com/zxlhhyccc/bf-package-master/trunk/zxlhhyccc/luci-app-control-guest-wifi

# D
# dnsfilter         基于dnsmasq的去广告程序
git clone --depth 1 https://github.com/kiddin9/luci-app-dnsfilter
# dockerman         Docker管理界面
svn co https://github.com/lisaac/luci-app-dockerman/trunk/applications/luci-app-dockerman

# F
# filebrowser       文件管理器
svn co https://github.com/immortalwrt/packages/trunk/utils/filebrowser
svn co https://github.com/immortalwrt/luci/branches/openwrt-18.06-k5.4/applications/luci-app-filebrowser

# H
# homebridge        米家的智能家居到Apple HomeKit的桥接
git clone --depth 1 https://github.com/shanglanxin/luci-app-homebridge
# HomeProxy         Tianling Shen主导的FQ
git clone --depth 1 https://github.com/immortalwrt/homeproxy
# Hyy2001X          软件库
git_sparse_clone https://github.com/Hyy2001X/AutoBuild-Packages.git master luci-app-adguardhome luci-app-natter luci-app-onliner luci-app-webd webd natter

# I
# ikoolproxy        广告过滤
git clone --depth 1 https://github.com/1wrt/luci-app-ikoolproxy.git && mv luci-app-ikoolproxy/koolproxy ./
# iperf             测速软件的luci界面
svn co https://github.com/Ysurac/openmptcprouter-feeds/trunk/luci-app-iperf
# iptvhelper        融合IPTV到家庭局域网
git clone --depth 1 https://github.com/riverscn/openwrt-iptvhelper && mvdir openwrt-iptvhelper
# irqbalance        修复lean的irqbalance
svn co https://github.com/openwrt/packages/trunk/utils/irqbalance

# L
# libtorrent-rasterbar
svn co https://github.com/immortalwrt/packages/trunk/libs/libtorrent-rasterbar
# linkease          易有云官方软件(易有云ddnsto,linkshare)
svn co https://github.com/linkease/istore/trunk/luci && mvdir luci
svn co https://github.com/linkease/nas-packages-luci/trunk/luci && mvdir luci
svn co https://github.com/linkease/istore-ui/trunk/app-store-ui
svn co https://github.com/linkease/nas-packages/trunk/network/services && mvdir services
svn co https://github.com/linkease/nas-packages/trunk/multimedia && mvdir multimedia
# lucky             大吉多种功能结合体
git clone --depth 1 https://github.com/sirpdboy/luci-app-lucky lucky1 && mvdir lucky1
# log 美化显示log
git clone --depth 1 https://github.com/hyy-666/luci-app-log

# M
# # MosDNS            插件化可定制的DNS转发器
# svn co https://github.com/QiuSimons/openwrt-mos/trunk/luci-app-mosdns
# svn co https://github.com/QiuSimons/openwrt-mos/trunk/mosdns
git_sparse_clone https://github.com/sbwml/luci-app-mosdns v5 luci-app-mosdns mosdns v2dat
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
# netdata
git clone --depth 1 https://github.com/sirpdboy/luci-app-netdata
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
# OpenAppFilter     内核级应用过滤
git clone --depth 1 https://github.com/destan19/OpenAppFilter && mvdir OpenAppFilter
# openclash         OpenWRT的Clash
svn co https://github.com/vernesong/OpenClash/trunk/luci-app-openclash

# P
# PassWall1&2       科学上网
git clone --depth 1 https://github.com/xiaorouji/openwrt-passwall-packages && mvdir openwrt-passwall-packages
git_sparse_clone https://github.com/xiaorouji/openwrt-passwall luci-smartdns-dev luci-app-passwall
git_sparse_clone https://github.com/xiaorouji/openwrt-passwall2 main luci-app-passwall2
# # pingcontrol       网络重连
# svn co https://github.com/koshev-msk/modemfeed/trunk/luci/applications/luci-app-pingcontrol
# svn co https://github.com/koshev-msk/modemfeed/trunk/packages/net/pingcontrol
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
git_sparse_clone https://github.com/fw876/helloworld/ main luci-app-ssr-plus lua-neturl redsocks2 shadow-tls
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
