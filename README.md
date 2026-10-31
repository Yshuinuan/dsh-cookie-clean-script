# DSH 启动 cookie 清理器

DSH 桌面版每次启动都会在本地随机端口起 Host，并签发一条 **30 天有效**的持久 cookie：

```
名称: dsh-auth-<sha256("127.0.0.1:<本轮端口")>
```

Chromium 会把它们全部留在 `%APPDATA%\@deepseek-ai\dsh-desktop\Network\Cookies` 里（cookie 不区分端口），每条约 226 字节。攒到约 70 条时，启动握手的 `Cookie` 请求头超过本地 Host 的 16 KiB 上限，服务端返回 **431**，界面报 `desktop welcome: Web authentication failed`，也就是「打不开」。

这个脚本只删掉这些 `dsh-auth-*` 记录，其他 cookie 原样保留，并在删除前备份。

## 用之前

先**完全退出 DSH**（含托盘图标 → 退出）。脚本检测到 cookie 库仍被占用时会直接退出（退出码 2），不会改任何东西。

## 需要配置什么吗？

不用。下载后直接双击 `clear-dsh-cookies.cmd` 就行，脚本会自己找位置：

- **cookie 库**：所有 Windows 安装都固定在 `%APPDATA%\@deepseek-ai\dsh-desktop\Network\Cookies`，不需要指向 DSH 的安装目录。
- **DSH 程序**（只有 `--launch` 会用到）：依次尝试 `--exe <路径>`、环境变量 `DSH_DESKTOP_EXE`、默认安装目录（`%LOCALAPPDATA%\Programs\DeepSeek Harness`、`%ProgramFiles%` 等），最后查卸载注册表里登记的安装路径。
- 实在找不到时：只清理、不启动，并提示你加 `--exe`。

系统要求：Windows；已安装 DSH 桌面版；Python 3（DSH 自带的运行时会被优先使用，自己装过 Python 也可以）。

## 用法

先预览（不改动）：

```powershell
.\clear-dsh-cookies.cmd --dry-run
```

确认后清理：

```powershell
.\clear-dsh-cookies.cmd
```

清理完顺手把 DSH 拉起来：

```powershell
.\clear-dsh-cookies.cmd --launch
```

## 每次启动自动清理

这个脚本不是常驻后台程序，而是一个**启动器**：你用它来开 DSH，它就会在启动前自动清一次。把这套动作固定成桌面图标即可。

### 方式一：自己新建快捷方式

1. 右键桌面 → 新建 → 快捷方式
2. 位置填：`"<脚本所在目录>\clear-dsh-cookies.cmd" --launch`（把 `<脚本所在目录>` 换成本文件夹的实际路径）
3. 名称随意，例如 `DeepSeek Harness (清理启动)`
4. 以后**只从这个图标启动 DSH**（原来的桌面/任务栏图标删掉或替换掉）；想固定到任务栏，把快捷方式拖到任务栏即可

> 仓库里不含 `.lnk` 文件：`.lnk` 是 Windows 快捷方式（就是桌面图标那个文件），里面记录的是**本机绝对路径**和图标，换台电脑就失效，所以仓库只提交脚本本体，快捷方式按上面步骤自建。

### 行为说明

- 每次双击：检查 cookie 库是否空闲 → 删除 `dsh-auth-*` → 启动 DSH。
- 如果 DSH 已经在运行，脚本会跳过清理，然后唤出已有窗口（Electron 单实例），不会开第二个。
- 如果提示 `still in use` 但窗口没出来，说明 DSH 还有后台进程（托盘图标没退），完全退出后再点一次。
- 支持固定到任务栏/开始菜单：把 `.lnk` 拖到任务栏即可。

## 参数

| 参数 | 作用 |
| --- | --- |
| `--db <路径>` | 指定 cookie 库（默认 `%APPDATA%\@deepseek-ai\dsh-desktop\Network\Cookies`） |
| `--dry-run` | 只统计、不删除 |
| `--launch` | 清理后启动 DSH 桌面版 |
| `--exe <路径>` | `--launch` 时启动哪个程序（默认自动查找） |
| `--force` | 跳过「正在使用」检查（不建议） |

## 安全说明

- 只执行一条 `DELETE FROM cookies WHERE name LIKE 'dsh-auth-%'`，其他站点的 cookie 不动。
- 删除前会在同目录生成 `Cookies.bak-YYYYmmdd-HHMMSS`，自动保留最近 5 份。
- 这个 cookie 只是本机 Host 的会话票据，**不是账号登录凭证**；删掉不会退出 DeepSeek 账号，下次启动会自动重新签发。
- 脚本需要 Python 3；优先使用 DSH 自带的运行时（`%USERPROFILE%\.dsh\dsh-runtimes\...\python.exe`），找不到再退回系统 `python`/`py`。

## 退出码

| 码 | 含义 |
| --- | --- |
| 0 | 成功（含「本来就干净」） |
| 2 | cookie 库被占用（DSH 还开着）或无法打开，未做修改 |
| 1 | 找不到 Python（由 `.cmd` 返回） |

> 这是官方修复前的缓解手段；等 DSH 更新后（例如握手改用非持久 session、启动时自清旧 cookie、或调大 `maxHeaderSize`），可以直接删掉这个目录。
