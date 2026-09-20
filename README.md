# Auto WorkFlows

自动化工作流集合，用于管理 [solarflows/openwrt-packages](https://github.com/solarflows/openwrt-packages) 仓库的插件采集、固件构建与上游源码同步。

> 📖 完整插件列表和来源请查看 [openwrt-packages 仓库 README](https://github.com/solarflows/openwrt-packages)

---

## 核心工作流 (Workflows)

| 工作流 | 文件 | 触发机制 | 说明 |
|:---|:---|:---|:---|
| **自建插件源更新** | [custom-feed.yml](.github/workflows/custom-feed.yml) | 每 12 小时定时 / Push / 手动触发 | 声明式管理 89 个第三方插件，多线程并发克隆、增量锁跳过、各分支专属 README 生成并推送到 `solarflows/openwrt-packages` |
| **官方上游同步** | [upstream-sync.yml](.github/workflows/upstream-sync.yml) | 每 12 小时定时 / Push / 手动触发 | 同步 lean / immortalwrt / QualcommAX 等上游分支，自动应用补丁与叠加层，使用 `--force-with-lease` 安全推送 |
| **规则数据更新** | [geodata-updater.yml](.github/workflows/geodata-updater.yml) | 每周六定时 / Push / 手动触发 | 自动拉取 Loyalsoldier 规则数据，多核并发生成标准 GFWList / AutoProxy 规则文件，自动更新 Makefile 叠加层 |
| **统一固件构建** | [firmware-build-unified.yml](.github/workflows/firmware-build-unified.yml) | Push / 手动触发 | 统一调度构建矩阵、变更检测、SDK/IB 缓存复用、多平台固件编译与 Release 发布 |

---

## 架构与目录组织 (Repository Structure)

仓库资源按工作流专属内聚组织，通用能力下沉至 Actions：

```text
.github/
├── actions/                         # 通用复合 Action (Composite Actions)
│   ├── apply-overlay/               # 统一文件叠加层 Action（支持 commit 控制）
│   ├── apply-patches/               # 统一补丁检验与应用 Action（带 gitlink 防污染）
│   └── git-auth/                    # 统一 Git 凭据安全注入 Action (GIT_ASKPASS)
├── custom-feed/                     # custom-feed 工作流专属资产
│   ├── packages.yaml                # 声明式软件包清单（单一事实源）
│   ├── readme-template.md           # 分支专属 README 模板
│   ├── patches/                     # 专用增量补丁（按 target 组织）
│   ├── patches-remove/              # 专用移除补丁
│   ├── overlay/                     # 专属叠加层（global/ 与 <target>/）
│   │   └── global/v2ray-geodata/    # v2ray-geodata 核心 Makefile
│   └── scripts/
│       ├── collect_packages.py      # 多线程并发克隆与增量提取引擎
│       └── generate_readme.py       # 分支专属 README 生成器（含 Commit SHA 链接）
├── upstream-sync/                   # upstream-sync 工作流专属资产
│   ├── patches/                     # {qualcommax, lede, packages, luci} 补丁
│   ├── overlay/                     # {packages} 专属叠加层
│   └── scripts/
│       └── retry_push.sh            # 通用安全推送脚本（租约比对与空提交检测）
├── archive/                         # 历史工作流与过时脚本归档
└── workflows/                       # GitHub Actions 入口文件
```

---

## 补丁与叠加层 (Patches & Overlay)

两类定制机制互不干扰，分工明确：

| 机制 | 适用场景 | 行为特点 |
|:---|:---|:---|
| **补丁（`patches/`）** | 上游已有文件的行级微调（1~10 行代码修改） | 保留为 `.patch` 文件；上游版本更新时支持模糊行号自适应（Fuzzy Offset Matching），最大化兼容上游迭代 |
| **叠加层（`overlay/`）** | 全新文件新增（如自定义 Makefile）或整文件彻底替换 | 目录结构与目标仓库相对路径完全一致，直接覆盖落位；优先级高于所有补丁；被叠加文件需手动维护 |

- `temp*.patch` 为临时补丁：应用失败仅告警跳过，不中断构建；其余补丁失败时快速报错（fail-fast）。
- 提交时自动进行 `gitlink (mode 160000)` 防护，杜绝嵌套子模块污染。
