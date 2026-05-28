<div align="center">

# 🚀 OpenWrt Packages

**自动化采集的 OpenWrt / ImmortalWrt 第三方插件集合**

[![Update Status](https://github.com/solarflows/AutoWorkflows/actions/workflows/OpenWRT_Packages_Updater.yml/badge.svg)](https://github.com/solarflows/AutoWorkflows/actions/workflows/OpenWRT_Packages_Updater.yml)

</div>

---

## 📦 分支说明

| 分支 | 目标平台 | 说明 |
|:-----|:---------|:-----|
| `main` | 通用 | 完整插件集合，包含所有主题和应用 |
| `qt6` | 通用 (Qt6) | 基于 Qt6 的插件集合 |
| `mt798x` | MediaTek MT798x | MT7981/MT7986 路由器专用 |
| `qualcommax` | Qualcomm Atheros | 高通平台路由器专用 |

## 🎯 使用方法

在你的 OpenWrt 构建脚本中添加：

```bash
git clone -b <branch> https://github.com/solarflows/openwrt-packages.git package/openwrt-packages
```

## 📖 完整插件列表

请查看 [AutoWorkflows 仓库 README](https://github.com/solarflows/AutoWorkflows#-插件来源) 获取完整的插件来源和说明。

## 🔄 更新频率

插件每 **12 小时** 自动更新一次（北京时间 0:00 和 12:00）。

**最近更新**: {{LAST_UPDATE}}

## 🙏 致谢

感谢所有开源社区和开发者的贡献！

---

<div align="center">

**如果这个项目对你有帮助，请给一个 ⭐ Star 支持一下！**

</div>
