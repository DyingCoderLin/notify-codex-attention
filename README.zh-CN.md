# notify-codex-attention

[English](README.md) | 简体中文

当 Codex CLI 需要你时，通过可点击的 macOS 浮窗提醒你，并快速返回运行该
Codex 会话的终端或 IDE。

> 不要再让 Codex 静静卡在审批、选择或输入步骤，而你还以为它正在工作。

## 为什么需要它

Codex 最适合在后台持续工作，真正影响效率的往往是人机交接：任务可能停在权限审批、
等待选择，或者已经完成，但这些状态没有及时引起你的注意。你去处理其他事情，Codex
却一直原地等待，直到很久以后才被发现。

`notify-codex-attention` 补上了这个闭环。它会在 Codex 真正需要你时主动提醒，概括下一步
需要处理的内容，并允许你点击浮窗快速回到承载该 Codex 会话的应用。它的核心贡献不只是
增加一个通知，而是消除 Codex 工作流中因遗忘和等待造成的时间浪费。

## 功能

- 在真实 Codex 权限审批时提醒
- 在 Codex 需要选择、文本输入或手动 UI 操作时提醒
- 在一轮 Codex 对话结束时提醒
- 区分“需要你处理”和“任务已完成”两种状态
- 点击后返回启动该 Codex CLI 的终端或 IDE 应用
- 普通工具调用和文件写入过程中不会打扰你
- 自动替换同一 Codex 会话的旧浮窗
- 使用原生 AppKit 浮窗，并提供 `terminal-notifier` 和 AppleScript 回退
- 不需要常驻服务、网络服务或第三方 Python 包

## 工作原理

三条事件路径共用同一个通知脚本：

1. 全局 Codex `notify` 回调负责一轮结束和最终提问。
2. `PermissionRequest` hook 负责真实权限审批。
3. 一条精简的全局 `AGENTS.md` 规则负责中途选择、请求输入和手动 UI 操作。

创建浮窗时，脚本会读取承载当前 Codex CLI 的应用所继承的 macOS bundle ID，并把目标
固定在这条浮窗中。因此，点击时不会根据当前前台应用或最近使用的应用进行猜测。macOS
终端和 IDE 集成终端都可以使用；如果某个宿主没有提供有效环境信息，也可以通过
`--activate-bundle` 显式指定。

## 环境要求

- macOS
- Codex CLI
- 一个终端应用或 IDE 集成终端
- Xcode Command Line Tools（`swiftc`）

如果没有 `swiftc`，请先安装命令行工具：

```sh
xcode-select --install
```

## 安装

### 1. 克隆 Skill

```sh
git clone https://github.com/DyingCoderLin/notify-codex-attention.git \
  "${CODEX_HOME:-$HOME/.codex}/skills/notify-codex-attention"
```

### 2. 编译原生浮窗

```sh
make -C "${CODEX_HOME:-$HOME/.codex}/skills/notify-codex-attention" build
```

该命令会为当前 Mac 架构生成 `scripts/codex-attention-overlay`。这个编译产物不会被 Git
跟踪。

### 3. 配置一轮结束提醒

在 `~/.codex/config.toml` 中加入以下配置。TOML 不会展开 `~` 或 `$HOME`，因此请把
`/Users/YOU` 替换为你主目录的绝对路径：

```toml
notify = ["/usr/bin/python3", "/Users/YOU/.codex/skills/notify-codex-attention/scripts/notify.py"]

[tui]
notifications = false
```

Codex 只支持一个全局 `notify` 命令。如果该配置已经被其他应用占用，请让它串联调用本
脚本，而不要添加第二个 `notify`。关闭 TUI 内建通知可以避免重复浮窗，不会关闭外部回调
或生命周期 hook。

### 4. 配置权限审批提醒

创建 `~/.codex/hooks.json` 并写入以下内容。如果文件已经存在，请把
`PermissionRequest` 合并进现有的 `hooks` 对象，不要覆盖原文件。请把 `/Users/YOU`
替换为主目录绝对路径：

```json
{
  "hooks": {
    "PermissionRequest": [
      {
        "hooks": [
          {
            "type": "command",
            "command": "/usr/bin/python3 \"/Users/YOU/.codex/skills/notify-codex-attention/scripts/notify.py\" --hook",
            "timeout": 10,
            "statusMessage": "Sending Codex attention notification"
          }
        ]
      }
    ]
  }
}
```

重启 Codex，运行 `/hooks`，然后信任这条准确的 hook 定义。Codex 会根据 hook 哈希记录
信任；定义发生变化时，需要重新审核。

### 5. 配置选择和输入提醒

在 `~/.codex/AGENTS.md` 中加入：

```md
- Before a mid-turn choice, requested input, or manual UI action, use `$notify-codex-attention`. Do not call it for permission approvals or final responses; the `PermissionRequest` hook and global `notify` callback own those.
```

修改全局配置后请重启 Codex。

## 权限说明

主要的原生浮窗不需要宽泛的 macOS 通知权限。请通过 `/hooks` 审核全局 hook，并且只批准
同时包含 `/usr/bin/python3` 和 `scripts/notify.py` 绝对路径的窄范围命令前缀。

可选的 AppleScript 和 `terminal-notifier` 回退通道可能会请求各自的 macOS 权限。

## 验证安装

运行编译和确定性测试：

```sh
make -C "${CODEX_HOME:-$HOME/.codex}/skills/notify-codex-attention" check
```

发送一条真实提醒：

```sh
cd "${CODEX_HOME:-$HOME/.codex}/skills/notify-codex-attention"
/usr/bin/python3 scripts/notify.py \
  --kind attention \
  --message "Codex 需要你处理当前任务" \
  --session-id "manual-test"
```

点击浮窗，确认能够返回运行当前 Codex CLI 的应用。

在不显示浮窗的情况下检查宿主路由：

```sh
/usr/bin/python3 scripts/notify.py \
  --kind attention \
  --message "路由测试" \
  --dry-run
```

输出中的 `activate` 应当是当前宿主应用的 bundle ID。如果宿主没有提供有效环境信息，
可以传入 `--activate-bundle com.example.Terminal`。

## 更新

```sh
git -C "${CODEX_HOME:-$HOME/.codex}/skills/notify-codex-attention" pull --ff-only
make -C "${CODEX_HOME:-$HOME/.codex}/skills/notify-codex-attention" build
```

## 卸载

删除 `~/.codex/config.toml` 中的 `notify` 配置、`~/.codex/hooks.json` 中的
`PermissionRequest` 配置，以及 `~/.codex/AGENTS.md` 中对应的规则，然后删除 Skill
目录。

## 仓库结构

```text
.
├── README.md
├── README.zh-CN.md
├── SKILL.md
├── agents/
│   └── openai.yaml
├── scripts/
│   ├── codex_attention_overlay.swift
│   └── notify.py
├── tests/
│   └── test_notify.py
└── Makefile
```

## 开发

```sh
make build   # 编译原生浮窗
make check   # 编译、检查 Python 语法并运行测试
make clean   # 删除本地生成的构建产物
```
