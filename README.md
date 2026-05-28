# Auto WorkFlows

自动化工作流集合，用于管理 [solarflows/openwrt-packages](https://github.com/solarflows/openwrt-packages) 仓库的插件采集、固件构建和上游同步。

> 📖 完整插件列表和来源请查看 [openwrt-packages 仓库 README](https://github.com/solarflows/openwrt-packages)

## Workflows

| 工作流 | 说明 |
|:-------|:-----|
| **OpenWRT Packages Updater** | 每 12 小时自动采集插件并推送到 openwrt-packages 仓库各分支 |
| **ImmortalWrt Builder** | 构建 mt798x / qualcommax 固件并发布 Release |
| **SDK Package Builder** | 使用 SDK 编译指定架构的 ipk 包 |
| **v2ray-geodata Updater** | 每周六更新 geodata 路由数据 |
| **Sync_Push** | 同步 lean / immortalwrt 等上游仓库并应用补丁 |
