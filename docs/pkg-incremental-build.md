# 按需编译演进计划（Package-Grained Incremental Build）

> 状态：设计已定稿，P1 已实现待验证，P2/P3 未实施
> 关联：`firmware-build-unified.yml`（plan）、`compile-packages.yml`（executor）、`docs/todo.md`（台账）
> 最后核对：2026-09-24

## 0. 目标

把 CI 从"每个 target 全量编译"演进为"只重编真实变更的软件包"：
- **plan 做全部决策**（什么变了、走哪条路径、编哪些包）
- **executor 只忠实执行**（编译、发布、数据采集），不做自治决策

## 1. 包级指纹检测（P1）

### 数据来源：`packages.lock.json`

- `custom-feed.yml` → `collect_packages.py` 已为每个 target 生成 `{pkg: {repo, branch, commit}}` 并随 feed 分支提交
- 注意：OpenWrt 构建系统**没有**集中的包 commit 输出文件（包级 commit 分散在各 Makefile 的 `PKG_SOURCE_VERSION`，且多数包用 release tarball 而非 git 源），`packages.lock.json` 是必要的人工制品

### 检测逻辑（plan 侧 `Load targets & check changes`）

```
feed HEAD (git ls-remote) 变了？
  └─ smart 触发 → 读 openwrt-packages@branch 的 packages.lock.json
       └─ 与 build-state.packages 逐包比对 commit SHA
            ├─ 全一致 → 撤销 feed 级变更信号，跳过
            ├─ 有变更 → 求"变更包 ∩ sdk.config 包"交集
            │     ├─ 交集非空 → CHANGED_PACKAGES_FINAL = 交集
            │     └─ 交集为空但变更包在 sdk.config 之外 → 升级全量（SDK 无该包目录）
            └─ lock 无 target 条目 → 回退 `*`（全量）
```

### 触发方式语义

| trigger | sdk_packages | 含义 |
|---|---|---|
| `smart` | 变更包子集 | 正常增量 |
| `smart` + 无变更 | `""` | 跳过 SDK 编译 |
| `full` / `sdk-packages` | `*` | 显式要求全量，由 sdk.config 控制 |
| sdk-ib | 变更包子集（`*` 或交集） | 只重编变更包注入 IB |

## 2. 状态回写闭环

```
executor compile 步骤:
  packages.lock.json (从 checkout 的 pkgs-feed 本地读)
    → 扁平化为 {pkg: "commit"} 写入 build-info.json
persist-state:
  merge 步骤把 .packages 字段回写 IMMWRT_BUILD_STATE
下一轮 plan:
  build-state.packages 作为 LAST_PKG_MAP 逐包比对
```

## 3. 逐包数据采集（P1）

executor 编译循环对每个包记录：
- `wall_sec`：墙钟耗时（`date +%s` 差值）
- `exit`：make 退出码
- `compile_time`：`logs/<pkg>/compile.txt` 末行 `time: real#user#sys`
- `version`：`make package/<pkg>/val.PKG_VERSION`
- `artifacts`：编译后产出的 ipk/apk 文件名列表

输出：`📊 逐包编译报表` Markdown 表格写入 step summary；JSON 通过 `packages_report` output 传递。

## 4. P2：plan 下传 SDK/IB 文件解析（已设计未实现）

### 动机
executor 目前自下载 `sdk-index.json`/`ib-index.json` 并 jq 排序选最新条目，这是决策（选哪个文件）而非执行（下载文件）。

### 方案
- plan `Decide build mode` 已用 `probe_index` 下载并校验 index，扩展其提取 file/version/sha256/source_sha 写入 matrix
- executor 新增 input：`matrix_sdk_file`/`matrix_sdk_version`/`matrix_sdk_sha256`/`matrix_sdk_source_sha`/`matrix_ib_file`
- executor 的 `Resolve SDK file name`（约 97 行）删减为直接透传 output；`Resolve IB file`（约 26 行）同理
- 预计净 -70 行

## 5. P3：保留 executor 自治的部分（有意为之）

| 保留 | 理由 |
|---|---|
| `Setup Signing Key` | 需 SDK tarball 实际的 `Config-build.in` 探测 APK/IPK，plan 无该数据 |
| cache restore/save/purge 的 key 计算 | 深度依赖步骤间 `cache-hit` 输出与 namespace 语义，上移收益低风险高 |
| `Build Log Analysis` / `ccache Stats` | 展示用途，非决策 |

## 6. sdk-ib 触发条件（现状）

必须同时满足（任一不满足降级全量）：
- `cache_strategy == smart` 且 `trigger == smart`
- `source_changed == false`（源码 fork HEAD 未变）
- `packages_changed == true`（插件 feed HEAD 变了）
- `standard_packages_changed == false`
- `config_changed == false`（seed/targets.json 未变）
- SDK/IB index 均存在且同版本同 source_sha

## 7. 已落地 commit 清单

| Commit | 内容 |
|---|---|
| `4c0d45c4` | 移除 sdk-cache-lookup 冗余预查步骤 |
| `455421e0` | SDK 编译前屏蔽 kmod 包防止触发内核全模块重编 |
| `1dad4519` | 包级指纹变更检测 + plan 下传包子集 + 逐包数据采集 + persist-state 回写 |

## 8. 待验证项

- [ ] sdk-ib 真实触发一次验证：变更包子集 + IB 注入 + 未变更包保留旧版本
- [ ] smart 无变更路径：plan 判定跳过，0 executor
- [ ] 变更包在 sdk.config 之外 → 升级全量的分支
- [ ] P2 实施（SDK/IB 文件解析上移）
