# 按需编译演进计划（Package-Grained Incremental Build）

> 状态：设计已定稿，P1/P2 已实现待验证（2026-09-26 指纹源重构为 tree SHA），P3 未实施
> 关联：`firmware-build-unified.yml`（plan）、`compile-packages.yml`（executor）、`docs/todo.md`（台账）
> 最后核对：2026-09-26

## 0. 目标

把 CI 从"每个 target 全量编译"演进为"只重编真实变更的软件包"：
- **plan 做全部决策**（什么变了、走哪条路径、编哪些包）
- **executor 只忠实执行**（编译、发布、数据采集），不做自治决策

## 1. 包级指纹检测（P1）

### 数据来源：构建输入真值锁（tree SHA）

指纹锚点是**实际进构建的内容**，而非上游仓库滚动 HEAD：

- **custom feed**（`solarflows/openwrt-packages@<branch>`，clone 到 `package/<feed>`）：
  顶层目录的 git tree SHA（内容寻址，目录内容不变则指纹不变）。plan 侧用 trees API
  一次取全部目录（per-branch 缓存），executor 侧本地 `git ls-tree HEAD`——同一 git
  对象，SHA 天然一致。`packages.lock.json`/README 等 root 文件是 blob 不是目录，天然
  排除；上游仓库无关提交（如 openwrt/packages master 的 rsync/banip 更新）不再触碰指纹。
- **上游 feeds**（源码分支 `feeds.conf.default` 定义；有锁分支按锁、无锁按默认 HEAD）：
  `git ls-remote` 比 state.feeds_sha，变了才 compare API 取变更文件 → 包名
  （≥3 级路径取第 2 级，2 级路径取第 1 级，兼容 openwrt/packages 与 routing 两类布局），
  **剔除被 custom feed 覆盖的包**（`scripts/feeds` install 对已存在的本地 srcpackage
  直接跳过，构建不用上游副本）。
- 历史：2026-09-25 前用 `packages.lock.json` 逐包上游 commit 比对，run `36211341719`
  实证其锚上游仓库 HEAD——openwrt/packages master 的无关提交翻转 tailscale 指纹致
  mt798x 误判全量，遂重构。`packages.lock.json` 文件保留（collect_packages.py 收集
  增量跳过仍依赖），plan 不再消费。

### 检测逻辑（plan 侧 `Load targets & check changes`）

```
任一 feed HEAD 变了（custom / 标准 packages / 上游 feeds）？
  └─ smart 触发 → 汇总变更包集合：
       custom feed: 目录 tree SHA 对比 → ΔC
       标准/上游 feed: compare diff → 包名 → 剔除 ∈ custom feed 目录 → ΔF'
       集合 = ΔC ∪ ΔF'
            ├─ 集合为空 → 撤销全部 feed 级变更信号，跳过
            │    （含「HEAD 变了但 diff 仅根级非包文件或全被 custom feed 覆盖」，
            │      视为不影响构建输入——设计取舍，非遗漏）
            ├─ diff 不可测（compare 超 250 文件 / conf 不可读 / 无基线）→ 回退 `*`（全量）
            └─ 非空 → 求"变更包 ∩ sdk.config 包"交集
                  ├─ 交集非空 → CHANGED_PACKAGES_FINAL = 交集
                  └─ 有包在 sdk.config 之外 → 升级全量（SDK 无该包目录）
```

### 基线闸门（防 skip 死锁）

`feed_trees`/`feeds_sha` 只由 executor 构建后回写。若 state 无 `feeds_sha` 基线时
仍判「无变更」，plan 会永久 skip → 基线永远建立不起来 → 上游 luci 无限漂移不触发。
故与 `config_sha` 无基准同语义：**无 `feeds_sha` 基线 → 强制全量建基线**；
`feeds.conf.default` 不可读同样回退全量（与 kernel 检测「不可测降级」同模式），
不静默跳过。首轮升级后预期全量一次，属正常行为非 bug。

### 触发方式语义

| trigger | sdk_packages | 含义 |
|---|---|---|
| `smart` | 变更包子集 | 正常增量 |
| `smart` + 无变更 | `""` | 跳过 SDK 编译 |
| `full` / `sdk-packages` | `*` | 显式要求全量，由 sdk.config 控制 |
| sdk-ib | 变更包子集（`*` 或交集） | 只重编变更包注入 IB |

## 2. 状态回写闭环

```
executor (compile-firmware / compile-packages):
  custom feed → git ls-tree HEAD → {pkg: tree_sha} 写入 build-info.json.feed_trees
  feeds update 后各 feed → git rev-parse HEAD → {feed: sha} 写入 build-info.json.feeds_sha
persist-state:
  merge 步骤回写 IMMWRT_BUILD_STATE 的 feed_trees / feeds_sha
  （并清除旧 .packages 逐包上游 commit 字段）
下一轮 plan:
  feed_trees 作 LAST_TREES 对比；feeds_sha 作上游 feed HEAD 基线
```

## 3. 逐包数据采集（P1）

executor 编译循环对每个包记录：
- `wall_sec`：墙钟耗时（`date +%s` 差值）
- `exit`：make 退出码
- `compile_time`：`logs/<pkg>/compile.txt` 末行 `time: real#user#sys`
- `version`：`make package/<pkg>/val.PKG_VERSION`
- `artifacts`：编译后产出的 ipk/apk 文件名列表

输出：`📊 逐包编译报表` Markdown 表格写入 step summary；JSON 通过 `packages_report` output 传递。

## 4. P2：plan 下传 SDK/IB 文件解析（已实现，🟨）

### 动机
executor 原本自下载 `sdk-index.json`/`ib-index.json` 并 jq 排序选最新条目，这是决策（选哪个文件）而非执行（下载文件）。

### 实现
- plan `Decide build mode`：`probe_index` 成功后，从 `/tmp/{sdk,ib}-probe-<target>/selected.json` 提取 `file`/`key`(version)/`sha256`/`source_sha`，写入 `target_plan.json` 并传至 `run-sdk-ib`/`run-packages` matrix 字段
- executor 新增 input：`matrix_sdk_file`/`matrix_sdk_version`/`matrix_sdk_sha256`/`matrix_sdk_source_sha`/`matrix_ib_file`/`matrix_ib_version`
- executor `Resolve SDK file name`：plan 值不为空时直接透传 output（跳过 gh release download + jq 排序）；为空时保留本地自解析回退
- executor `Resolve IB file`：同上
- `Setup Signing Key` 不移动（需读取实际 SDK tarball 的 `Config-build.in`，plan 无该数据）
- 净效果：plan 侧新增 6 个变量提取与 6 个 jq 条件字段；executor 侧 `Resolve SDK file name`/`Resolve IB file` 变为"plan 值优先透传 + 本地回退"结构，删除了独立的二次决策逻辑

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
- `packages_changed == true`（变更包集合非空：custom feed Δ ∪ 标准/上游 feed Δ'）
- `config_changed == false`（seed/targets.json 未变）
- SDK/IB index 均存在且同版本同 source_sha

注（2026-09-26 起）：标准 packages feed 与上游 feeds（luci/routing/telephony/video）的
变更折入变更包集合走同一交集路由，不再一刀切强制全量；被 custom feed 覆盖的包
（scripts/feeds 本地优先）不参与判定。

## 7. 已落地 commit 清单

| Commit | 内容 |
|---|---|
| `4c0d45c4` | 移除 sdk-cache-lookup 冗余预查步骤 |
| `455421e0` | SDK 编译前屏蔽 kmod 包防止触发内核全模块重编 |
| `1dad4519` | 包级指纹变更检测 + plan 下传包子集 + 逐包数据采集 + persist-state 回写 |
| `87473989` | sdk-ib 接受 plan 下传变更包子集并求 sdk.config 交集 |
| `b816ebe4` | 本计划文档落地 |
| 本组提交 | P2：SDK/IB 文件解析上移 plan，executor 透传（保留本地回退） |
| 本组提交 | 指纹源重构：packages.lock 逐包上游 commit → tree SHA 真值锁 + 上游 feeds 检测（G11），state `packages`→`feed_trees`/`feeds_sha` |

## 8. 待验证项

- [ ] sdk-ib 真实触发一次验证：变更包子集 + IB 注入 + 未变更包保留旧版本
- [ ] smart 无变更路径：plan 判定跳过，0 executor
- [ ] 变更包在 sdk.config 之外 → 升级全量的分支
- [ ] P2 透传路径：plan 指定 SDK/IB 文件后 executor 跳过 index 自解析（本地回退分支也应保持可用）
- [ ] tree SHA 指纹：首轮建基线全量 → 次轮精确到变更包（run `36211341719` 后回归验证）
- [ ] 上游 feed 变更路径：luci/routing HEAD 变化触发检测、被 custom feed 覆盖的包不触发
- [ ] 基线闸门：state 无 feeds_sha 时即使各 feed HEAD 均未变也强制全量（建基线），次轮起正常增量判定——首轮全量是预期行为，勿误判为 bug
- [ ] 根级非包文件变更（feed 根 Config.in/README）：不触发构建（设计取舍），日志应显示撤销信号而非全量
- [ ] IB 组装两阶段包选择：seed 请求含 kconfig 丢弃的包时剔除重试（run `36211341719` ipq807x 回归：5 个 led kmod 剔除后应成功）
- [ ] plan step 拆分后（21000 字符限制）三 step 串行数据流：stage.jsonl → pkg_stage.jsonl → target_changes.json，决策 step 消费不变
