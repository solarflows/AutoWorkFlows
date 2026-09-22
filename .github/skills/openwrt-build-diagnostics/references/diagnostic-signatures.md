# 诊断特征库

## `time:` 行不能判定失败包

证据：

- 失败的 `compile.txt` 以 `time: package/.../compile#...` 结尾
- job 或摘要声称未发现失败包，但构建明显失败

解读：`scripts/time.pl` **无论命令退出状态如何**都会打印计时行——它计算耗时、打印 `%s#%.2f#%.2f#%.2f\n`，然后才以子进程状态退出。失败的构建因此也以 `time:` 行结尾。失败包的权威来源是 `logs*/<pkg>/error.txt`（`ERROR: <pkg> failed to build.`）。末行检查仅作为中断日志的兜底。

## 通用环境变量泄漏

证据：

- `continue configure in default builddir "./<matrix-target>"`
- `--enable-builddir=<matrix-target>`
- 某 workflow 或进程导出了通用的 `TARGET`、`HOST` 或 `BUILD` 值

解读：被继承的环境变量改变了 Autoconf 或其它构建工具的约定输入。改动包代码前先核实来源环境。

## libffi InstallDev 头文件缺失

证据：

- `cp: cannot stat .../<gnu-target>/fficonfig.h`
- 首轮 configure 选择了以固件矩阵 target 命名的目录
- 重试的 `compile.txt` 很小或直接跳到 InstallDev

解读：libffi 在错误的构建目录下生成了 `fficonfig.h`。已验证的 mt798x 案例中，job 级 `TARGET=mt798x` 覆盖了 Autoconf 预期的 target 目录。

## Stamp 跳过重试

证据：

- 重试日志远小于对应的首轮日志
- 重试直接到达 staging 或 InstallDev，没有 configure 与编译输出
- `logs.1` 包含更早的 configure 或编译器活动

解读：重试复用了 stamp，不含原始失败原因。优先诊断 `logs.1`。

## ccache 环境不匹配

证据：

- 缓存恢复或 ccache 设置被禁用时，包装器变量仍在导出
- 编译器命令意外地被双重包装
- 空缓存或不兼容缓存与包装器配置变更同时出现

解读：独立检查 seed 级 `CONFIG_CCACHE`、workflow 包装器导出、恢复行为与策略选择。不要仅凭低命中率推断因果。

## GitHub `needs` 跳过

证据：

- 下游 job 未评估自身条件即被跳过
- 其 `needs` 包含一个被跳过的 job

解读：GitHub 会隐式跳过依赖了被跳过 job 的 job。仅当确实需要依赖结果时才用 `always()` 加显式结果判断。

## 不可执行的 `src/configure` 被静默跳过

证据：

- 编译阶段出现 `make[4]: *** No targets specified and no makefile found. Stop.`，且是整个构建中唯一出现该特征的包
- 首轮 `compile.txt` 显示 patch + autoreconf，随后直接跳到 `make[4]`，没有任何 `checking for...` 的 configure 输出
- 包 Makefile 没有 `PKG_SOURCE_URL`；源码来自仓库内的 `src/` 目录（`unpack.mk` 把空 `PKG_SOURCE` 视为 `PKG_UNPACK=true`；`package-defaults.mk` 把 `src/.` 拷入构建目录）
- `src/configure` 在 feed git 树中的模式是 100644（可通过 GitHub trees API 验证）

解读：`Build/Configure/Default` 以 `if [ -x ./configure ]` 为守卫；不可执行的 configure 被静默跳过（无输出、exit 0、`.configured` stamp 照常创建），于是编译阶段找不到 Makefile。带 `PKG_FIXUP:=autoreconf` 时，若 quilt 补丁重新触及 configure 文件，根目录的 `autoconf` 步骤也会被跳过（`|| true` 吞掉错误），陈旧的 configure 永远不会重新生成。仅 `chmod +x` 不够——若 configure 内容已陈旧（如依赖是 `+libpcre2` 却在检测 pcre v1），它会以可见的 configure 错误失败。修复：在包 Makefile 注册 `Hooks/Prepare/Post`，在 quilt 应用完全部补丁后删除 `$(PKG_BUILD_DIR)/configure`，强制 autoreconf 从 `configure.ac` 重新生成（内容正确且 autoconf 会设置可执行位）。不要直接在 feed 里删除 `src/configure`：构建时 0001 quilt 补丁会修改该文件，删除会破坏补丁应用。已验证案例：run 31559354153（mt798x），包 `shadowsocksr-libev` 来自 `Openwrt-Passwall/openwrt-passwall-packages`。

## 缓存命中仍重编工具链

证据：

- `Restore toolchain cache` 日志显示 `Cache restored from key: immwrt-v2-toolchain-...`（真实命中，不是前缀未命中）
- `Prepare toolchain & ccache` 步骤仍出现 `make[2] -C tools/... compile` 与 `make[2] -C toolchain/... compile` 行，且耗时几十分钟
- warm-cache 与冷运行的 `Prepare` 耗时接近（已验证 run 34805493661：ipq807x warm 40m28s vs cold 46m37s；GCC 14 目标最严重）

解读：恢复的工具链缓存只含 `staging_dir/host*` + `staging_dir/tool*`，不含 `build_dir/`——各 host 工具的 `.built` 标记在 `build_dir/` 里（`include/host-build.mk` 的 `HOST_STAMP_BUILT`）。执行子目录目标（`make tools/compile toolchain/compile`）会绕过顶层 `$(tools/stamp-compile)` / `$(toolchain/stamp-compile)` 守门，make 逐工具检查空 `build_dir` 中缺失的 `.built` 依赖并重编整个工具链。只有默认 `make` 目标（`world` → `prepare`）通过 `timestamp.pl` 查询 stamp 并在数秒内跳过整棵子树。修复方向：缓存命中时绝不调用子目录目标；依赖顶层 stamp；仅当 `staging_dir/host/bin/ccache` 确实缺失时才构建 `tools/ccache/compile`。

## 递归 `dl` 清理破坏 Go/Rust 模块缓存

证据：

- Go 包在 `dl/go-mod-cache/<module>@<version>/` 内报 `pattern <file>.binpb: no matching files found`（已验证：protobuf `editions_defaults.binpb`，run 34940720655）
- Rust 报 `failed to calculate checksum of: .../vendor/<crate>/Cargo.toml.orig` / `No such file or directory`（已验证：`cc-1.2.28`）
- 失败集中在 Go/Rust 密集型包（`sing-box`、`hysteria`、`v2ray-plugin`、`xray-core`、`geoview`、`rust [host]`），同 run 的 C/C++ 包成功

解读：残损下载清理执行了不带 `-maxdepth` 的 `find dl -size -1024c`，递归进入 `dl/go-mod-cache` 与 `dl/cargo`（共享模块缓存，含大量合法的小于 1KB 文件：Go `//go:embed` 资源、cargo checksum 伴随文件）。每次循环迭代都重新删除，一次重试就毒害后续所有 Go/Rust 包。此类清理必须限定为 `find dl -maxdepth 1 -type f -size -1024c`。