# Terminal Auto-Approve 配置

本 skill 的终端操作收敛为 `.github/skills/openwrt-build-diagnostics/scripts/` 下两个 Python 脚本的五个固定子命令，可用少量精确规则覆盖：

```text
python .github/skills/openwrt-build-diagnostics/scripts/fetch_build_logs.py list
python .github/skills/openwrt-build-diagnostics/scripts/fetch_build_logs.py artifacts --run-id <id>
python .github/skills/openwrt-build-diagnostics/scripts/fetch_build_logs.py fetch   --run-id <id> [--artifact <name>] [--pattern <glob>] [--case <case-id>]
python .github/skills/openwrt-build-diagnostics/scripts/fetch_build_logs.py extract --archive <path> --case <case-id>
python .github/skills/openwrt-build-diagnostics/scripts/analyze_build_logs.py .diagnostics/openwrt-build/<case-id>
```

## 推荐条目

合并到 User 级 `settings.json` 的 `chat.tools.terminal.autoApprove`：

```jsonc
{
    // fetch 入口：只批准四个固定子命令
    "/^python(3)?(\\.exe)?\\s+\\.github\\/skills\\/openwrt-build-diagnostics\\/scripts\\/fetch_build_logs\\.py\\s+(list|artifacts|fetch|extract)(\\s|$)/": true,
    // analyzer：只批准读取诊断目录
    "/^python(3)?(\\.exe)?\\s+\\.github\\/skills\\/openwrt-build-diagnostics\\/scripts\\/analyze_build_logs\\.py\\s+\\.diagnostics\\/openwrt-build\\//": true,
    // 高成本与破坏性参数退回人工确认（命令行级 deny 优先于子命令级 allow）
    "/\\s--(force|all-artifacts)(\\s|$)/": { "approve": false, "matchCommandLine": true },
    "/\\s--max-mb(\\s+|=)0\\b/": { "approve": false, "matchCommandLine": true }
}
```

若你的环境用 `py -3` 启动，把前缀改为 `^(python(3)?|py(\\s+-3)?)(\\.exe)?`。

## 生效范围（先读）

- 规则只在权限级别为 `default` / `assisted`，且未开启会话级批准时参与判定。
- 权限级别为 `autoApprove` 或 `autopilot` 时，VS Code 会把终端规则分析器（`ODe`）整体从分析链中移除（`WDe` + `RK`），**allow 与 deny 全部跳过**。
- 会话级「允许本会话」(`setChatSessionAutoApproval`) 同样在分析器入口短路，直接批准。
- `chat.tools.global.autoApprove`（其自带描述称为 "YOLO mode"）声明关闭所有工具、所有工作区的人工批准。
- 结论：这里的 deny 不是最后防线，只在正常模式有效；不可逆操作的真正保障来自脚本自身的只读约束与人工复核。

## 匹配语义（依据 VS Code 内置实现）

- 前置条件：`chat.tools.terminal.enableAutoApprove` 为 `true`（默认值）。
- 规则分为四类：逐子命令的 allow/deny，与整条命令行的 allow/deny（由对象形式的 `matchCommandLine: true` 指定）。
- 判定顺序：① 任一子命令 deny → 拒绝；② 整行 deny → 拒绝；③ 所有子命令都 allow → 静默批准；④ 其余 → 询问。因此命令行级 deny 能拦住已被 allow 规则批准的命令。
- 键为 `/pattern/flags` 时按正则匹配；本条目省略 `matchCommandLine`，因此按“逐个子命令”匹配，正则从子命令开头锚定 `^python`。
- 键为普通字符串且含 `/` 或 `\` 时，按路径前缀匹配并同时兼容 `./`、`/` 与 `\`（例如 `bin/test.sh` 同时匹配 `bin\test.sh`、`./bin/test.sh`）；本 skill 使用正则形式以避免平台差异。
- 命令一旦含 `|`、`&&`、`;`、重定向、`$(...)` 等组合符，会被拆成多个子命令分别判定，且各部分都要命中 allow 规则；本 skill 的命令刻意保持“单行、单命令、无分隔符”，因此一条正则即可覆盖。
- 以 `NAME=value` 开头的命令（瞬时环境变量）一律拒绝，与规则无关。
- 若自定义了更宽的 deny 规则（如 `"/\\.py/i": {approve:false, matchCommandLine:true}`），它会先于本条目命中；出现被拒绝提示时先检查此类冲突。
- 若设置 `chat.tools.terminal.ignoreDefaultAutoApproveRules: true`，内置默认规则被忽略，必须显式添加所需条目。
  已验证语义：只剔除「键未在任何配置层显式出现」的默认条目；显式写出的同值条目仍然生效，
  未显式写出的内置规则（如 sed 写文件检测正则）会失效。改为 `false` 可保留内置规则，
  用户自定义值仍然优先覆盖同键默认值。
- 命令使用仓库根目录相对路径且分隔符必须是 `/`（`python .github/...`）；不要改写为绝对路径或反斜杠形式，否则需按机器重写规则。
- 命令从仓库根目录执行；脚本通过 `__file__` 定位仓库与 `.diagnostics/`，与当前工作目录无关。

## 治理

- 规则锚定「路径 + 动词」，不锚定文件内容：新增脚本、新增子命令或新增参数都必须重新评估本文件规则，尤其是会写入、下载或删除的子命令。
- 规则是路径字符串匹配且跨仓库生效：任意仓库中同路径脚本都会被批准。若不能接受该暴露面，改用会话级批准。
- 不要把 `chat.tools.terminal.autoApprove` 写入仓库 `.vscode/settings.json`：该设置为 `restricted`，仅 User 级生效，仓库内写入不会起作用。
- 重命名脚本或移动 skill 目录时，必须同步更新规则，否则诊断流程会退回逐条询问。

## 安全边界

`fetch_build_logs.py`：

- 只调用 `gh auth status`、`gh repo view`、`gh run list`、`gh run view`、`gh api`（GET）、`gh run download`，不触发 workflow、不修改 Releases、不写远端数据。
- 本地写入仅限 `<repo>/.diagnostics/openwrt-build/<case-id>/`（`.diagnostics/` 已在 `.gitignore` 中）。
- 解压防护：跳过 symlink/hardlink 成员、跳过含 `build_dir` 组件的路径、拒绝绝对路径与 `..` 穿越、限制解压总量（`--max-mb`，默认 2048 MB）。
- `--max-mb` 只约束嵌套解压，不约束 `gh run download` 本身；大 artifact 需先确认再下载，避免误拉数 GB 的固件包。

`analyze_build_logs.py`：

- 只读取 case 目录，输出写入 `<case>/report/summary.md` 与 `analysis.json`，不修改输入日志。

其余保护不受影响：用户自定义的 `rm` / `Remove-Item` / `curl` 等 `false` 条目仍然保留，自动批准只覆盖上述两个只读诊断脚本。

## 可选：与项目安全规则对齐的条目

`AGENTS.md` 与 `.github/instructions/workflow-agent-common.instructions.md` 要求：未经明确授权不得 commit / push / rebase / tag / 触发远程 workflow / 修改 Release / 读取或打印密钥。以下条目按「只读放行、写操作降级」划分，按需取用：

```jsonc
{
    // allow：只读高频查询
    "/^gh\\s+(run|pr|issue|repo|workflow|release)\\s+(list|view|diff|checks|status)\\b/": true,
    "/^gh\\s+auth\\s+status\\b/": true,
    "/^gh\\s+cache\\s+list\\b/": true,
    "/^gh\\s+api\\s+--paginate\\s+\\S+$/": true,
    "/^git\\s+(remote\\s+-v|rev-parse|describe|worktree\\s+list|stash\\s+list|for-each-ref|config\\s+--(get|list))\\b/": true,

    // deny：不可逆或高危（即使当次明确要求也会被拦截，需要时临时改动规则或手动执行）
    "/^git\\s+(push\\s+.*(-f|--force)|reset\\s+--hard|clean\\b|filter-branch|checkout\\s+\\.|restore\\b)/": { "approve": false, "matchCommandLine": true },
    "/^gh\\s+(run\\s+(rerun|cancel|delete)|workflow\\s+run|release\\s+(create|edit|delete|upload)|variable\\s+(set|delete)|secret\\s+(set|delete))/": { "approve": false, "matchCommandLine": true },
    "/^gh\\s+api\\b.*\\s(-X|--method|--field|--input|-f)\\b/": { "approve": false, "matchCommandLine": true },
    "/^gh\\s+run\\s+download\\b/": { "approve": false, "matchCommandLine": true },

    // deny：就地改写与密钥暴露
    "/^sed\\b[^|;]*(\\s-[a-zA-Z]*i[a-zA-Z]*\\b|--in-place)/": { "approve": false, "matchCommandLine": true },
    "/\\$env:(ACCESS_TOKEN|GH_TOKEN|GITHUB_TOKEN|APK_BUILD_KEY|USIGN_KEY)/i": { "approve": false, "matchCommandLine": true },
    "/(\\.ssh[\\\\/]|\\.aws[\\\\/]|\\.npmrc|\\.git-credentials|\\.env\\b|\\.pem\\b|APK_BUILD_KEY|USIGN_KEY)/i": { "approve": false, "matchCommandLine": true }
}
```

取舍说明：

- `git commit` / `git tag` / `git push` 未放入 deny：项目允许在你明确要求后执行，保留为询问态即可；只把不可逆操作（`reset --hard`、`clean`、`filter-branch`、强制推送、Release/run 删除）硬拒绝。
- 若已允许 `Get-Content` 或 `Get-*` 通配，务必保留密钥路径 deny：否则读取 `.ssh`、`.env`、`*.pem` 内容不会询问，而项目规则禁止向会话暴露密钥。
- 裸 `gh`（无上表子命令）默认仍会询问，属于预期行为。
