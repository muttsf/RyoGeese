<img src="app/assets/RyoGeese.png" alt="RyoGeese Logo" width="96">

# RyoGeese

[English](#english)

由手电加鞭制作的免费开源早期测试版。通过视觉识别读取独立Dash插件显示的信息，在本机给出技能推荐。本工具的初衷是代替魔兽世界本应好用的推荐技能，只可惜官方的推荐技能不好用，所以开发者希望代替官方的推荐技能，希望任何玩家都可以无痛使用更智能的一键宏输出。作者认为尤其适合在团本中使用，而且工具支持暂缓爆发功能，非常适合留爆发对于某阶段某对象使用。目前支持魔兽世界正式服12.1.5、暗牧以虚空编织者为主的纯单体循环，其他职业尚未实现，项目完成度提高后会尽快更新恶魔术等其他职业。

当前版本提供技能与按键提示，实际施放由玩家操作。

**[下载软件](https://github.com/muttsf/RyoGeese/releases) · [安装配套插件](https://github.com/muttsf/RyoGeese-Dash) · [反馈问题](https://github.com/muttsf/RyoGeese/issues)**

当前版本：**0.1.0-beta.4 测试版**。

喜欢这个项目的话，欢迎点个 **Star**，也欢迎通过 Issues 和 PR 一起改进。

## 循环来源与测试重点

内置循环参考 [SimulationCraft（SIMC）](https://github.com/simulationcraft/simc) 的暗牧单体技能优先级与机制资料，再结合 Dash 能显示、软件能识别的信息，整理为本机运行的循环实现。当前实现包含简化与近似，不是在后台运行完整 SIMC 模拟器，也不宣称所有场景与 SIMC 完全等价。当前参考资料固定在 [SIMC 提交 `3dcabb9`](https://github.com/simulationcraft/simc/tree/3dcabb94dd32f786786c67541dfd10db9f39e43b)。

导入你自己的 SIMC，是为了核对专精、天赋、装备和套装，并配置已支持的内置规则，不是导入一套新的循环。软件不绑定作者的角色、同一套装备或按键；循环由维护者更新、验证后，随软件版本发布。

目前已支持虚空编织者的主要技能及多项常用天赋组合；其他英雄树和部分未适配分支仍不支持，具体以导入核对结果为准。**能够载入不代表每个天赋细节都已验证完善。**

这是早期测试版，希望使用者重点测试和评估循环是否好用：

- 自己的实际 SIMC 能否正确核对，载入的配置是否符合预期。
- 技能顺序、DOT 维持、狂乱资源处理是否存在明显不合理的情况。
- 团本中暂缓爆发、为指定阶段或目标留爆发时，推荐是否符合预期。

反馈时请附天赋配置、发生时间和对应推荐日志，并删去不愿公开的个人信息。

## 下载与安装

第一次使用，需要分别安装**桌面软件**和**游戏插件**。

1. 打开[软件下载页](https://github.com/muttsf/RyoGeese/releases)，在附件 **Assets** 中下载名称以 **`x64-Setup.exe`** 结尾的安装包，运行并完成安装。普通用户不需要下载源码 ZIP。
2. 按照 [RyoGeese-Dash 的安装说明](https://github.com/muttsf/RyoGeese-Dash#安装插件)，把插件放入游戏的 `Interface/AddOns` 目录。
3. 进入游戏并启用 Dash，确认插件面板完整可见；打开 RyoGeese。也可以双击软件安装目录中的 **`点我启动.exe`**。

软件安装包不包含游戏插件，两者分别更新。当前软件测试版**未作数字签名**；请从本项目发布页下载，页面同时提供源码和 `SHA256SUMS.txt` 校验文件。

## 第一次使用

主页面按从上到下的四个步骤操作，完成前一步后会解锁下一步。

| 步骤 | 操作 |
| --- | --- |
| **1 · 导入 SIMC** | 在游戏中使用 SimulationCraft 插件输入 `/simc`，复制当前角色的完整导出。点击软件的“导入SIMC”，粘贴并确认。软件会核对职业、天赋和装备，并载入已支持的循环。 |
| **2 · 定位插件** | 保持游戏和 Dash 面板完整可见，点击“定位插件”，等待显示完成。 |
| **3 · 技能定位** | 点击“设置技能按键”，填写你实际使用的技能按键，例如 `1`、`E`、`Shift+1`。按键可以部分填写，也可以全部留空；打开过设置即可继续。 |
| **4 · 开始** | 勾选“确认配置，准备开始”，点击“开始推荐”。首次载入需要等待，完成后会出现推荐小窗。 |

SIMC 导出需要安装独立的 [SimulationCraft 游戏插件](https://github.com/simulationcraft/simc-addon)。软件会保存上次的 SIMC 和按键，之后可用“载入上次”；更换天赋或装备后，请重新导入当前角色资料。

## 推荐小窗

- **技能名称与按键**：显示当前收到的技能建议。未填写按键时，显示“鼠标点击”。
- **暂缓爆发／恢复爆发**：切换是否暂缓推荐爆发技能，右上角会显示当前状态。
- **极简**：切换为主要显示按键的小窗；双击小窗或按 `Esc` 返回标准模式。
- **重新定位**：移动插件或调整面板大小、字号后，点击此按钮重新定位。
- **退出**：关闭推荐小窗并结束本次推荐。

本版功能：每500毫秒安排取图，识别串行处理，显示当前技能建议。后续会考虑提升至300毫秒左右的版本，减少玩家使用读条技能后的空转等待。

实际取图间隔与处理耗时会受电脑负载影响。300毫秒属于后续优化计划，当前只显示第一推荐，没有下一招预测。

## 可选：导入技能图标

首版不附带游戏技能图片和网络音效。没有图标包时，技能名称与按键仍可正常使用，图标位置留空。

如果你已有符合规则的图标包，在主页面点击 **“导入图标包”**，选择 ZIP 文件即可，**无需解压或逐个设置**。更新时重新导入新包。

一个包可以包含多个职业的图标；这不代表软件已经支持这些职业的推荐循环。图标包制作规则见 [ICON_IMPORT.txt](ICON_IMPORT.txt)。

## 电脑与游戏要求

| 项目 | 当前范围 |
| --- | --- |
| 游戏 | 正式服 **12.1.5**，90 级，已适配的暗牧天赋；导入时会检查支持情况。 |
| 系统与显卡实测 | **Windows 11 + NVIDIA RTX 5080**。 |
| 其他 NVIDIA 显卡 | **RTX 30 系及以上为理论兼容目标**，没有逐型号实机验证。 |
| AMD | AMD CPU 可以使用；**AMD 显卡暂不支持**。 |
| 内存与运行环境 | **8GB 内存没有实机兼容保证**；显卡驱动及微软 Visual C++ x64 运行库需满足程序要求。 |

**作者补充：**

后续会想办法制作A卡的支持但是目前无法保证且没有A卡可以测试。个人第一次制作采用成熟的CUDA库工具，后续会想办法支持，并承诺蓝宝石7900XTX是世界上最美的显卡。

## 常见问题

**为什么新安装后还有上次的 SIMC？**<br>
角色资料和按键保存在本机用户目录，卸载时会保留，方便重新安装后继续使用。公开安装包不包含制作人的私人 SIMC、按键或日志。

**定位失败或移动了 Dash 怎么办？**<br>
确认游戏窗口和 Dash 面板完整可见，再点击“定位插件”或推荐小窗中的“重新定位”。调整位置、大小或字号后都需要重新定位。异常处理的具体范围见 [运行边界说明](app/运行边界说明.txt)。

**循环怎么更新？需要自己导入吗？**<br>
循环由维护者核对游戏补丁和 SimulationCraft 变化，验证后随软件版本发布。玩家下载新版软件即可，无需自行导入循环文件。当前不会在线自动更新循环。

**遇到问题怎么反馈？**<br>
点击主页面的“打开日志”，找到出问题时对应的“报错”或“推荐”记录，再到 [Issues](https://github.com/muttsf/RyoGeese/issues) 说明现象、软件版本、显卡型号和发生时间。提交日志前，请检查是否含有不愿公开的信息。

日志会分卷并清理已关闭的旧记录，约 **200MiB** 为清理目标；清理失败不会为了限制大小而阻塞推荐。

<details>
<summary>查看本机数据保存位置</summary>

- SIMC 与按键：`%LOCALAPPDATA%\AiHekili\startup\current.json`（沿用旧路径，兼容已有记录）。
- 报错与推荐日志：`%LOCALAPPDATA%\RyoGeese\logs`。
- 导入的图标：`%LOCALAPPDATA%\RyoGeese\icons`。

更新或卸载前，请退出主窗口和推荐小窗。插件设置由游戏单独保存。

</details>

## 开发与许可

欢迎提交 Issue 或 PR。建议一次处理一个问题，说明修改原因和验证结果；影响推荐、识别或安装流程的变更需要相应核验。

- [构建说明](BUILDING_PORTABLE.txt)：准备运行依赖、组装程序和构建安装器。当前需要自行提供清单匹配的依赖，尚无自动下载依赖的一键构建。
- [更新维护流程](MAINTENANCE.txt)：检查游戏补丁与 SIMC、验证并发布循环。
- `app/`：桌面界面、内置循环、视觉识别监督和参考资料。
- `native/`：独立 GPU 读取器源码；外部运行依赖的校验清单见 `DEPENDENCIES.json`。

自有源码采用 **GPL-3.0-only**；自有 GPU 读取器另有 NVIDIA／微软运行库附加许可。第三方组件保留各自许可，详见 [LICENSE](LICENSE)、[许可范围](LICENSING.md) 和 [第三方声明](app/notices/)。

---

## English

[返回中文 / Back to Chinese](#ryogeese)

A free, open-source early test release created by **手电加鞭**. It uses visual recognition to read information displayed by the separate Dash addon and provides ability recommendations locally on your computer. The project aims to replace World of Warcraft's built-in ability recommendations, which the author feels should have been useful but fall short in practice. The developer hopes to help any player use a smarter one-button macro-based damage rotation with minimal friction. The author considers the tool particularly suitable for raids: its **Hold Burst** feature lets you save burst cooldowns for a particular phase or target. The current release supports **Retail 12.1.5 · Shadow Priest · a pure single-target rotation focused on Voidweaver**. Other specializations are not yet implemented; Demonology Warlock and others are planned as the project matures.

The current version displays ability and keybind suggestions; players cast the abilities themselves.

**[Download desktop app](https://github.com/muttsf/RyoGeese/releases) · [Install companion addon](https://github.com/muttsf/RyoGeese-Dash#english) · [Report an issue](https://github.com/muttsf/RyoGeese/issues)**

Current release: **0.1.0-beta.4 test version**.

If you like this project, please consider giving it a **Star**. Issues and pull requests are welcome.

### Rotation sources and testing priorities

The built-in rotation is based on [SimulationCraft (SIMC)](https://github.com/simulationcraft/simc)'s Shadow Priest single-target priorities and mechanic data, adapted into a local implementation for the information available through Dash and the project's visual recognition. It contains simplifications and approximations; it does not run the full SIMC simulator or promise identical results in every situation. The current reference data is pinned to [SIMC commit `3dcabb9`](https://github.com/simulationcraft/simc/tree/3dcabb94dd32f786786c67541dfd10db9f39e43b).

Your SIMC export is used to check your specialization, talents, equipment, and set bonuses, and to configure the supported built-in rules. It is not a separate imported rotation. The software is not tied to the author's character, exact equipment, or keybinds. Maintainers update and validate the rotation, then distribute it with new software releases.

The current implementation supports Voidweaver's core abilities and several common talent variations. Other hero trees and some unimplemented branches remain unsupported; the import check determines whether a profile can be used. **Support for a profile does not mean every talent interaction has been fully validated.**

This is an early test release. Please focus feedback on whether the rotation is useful in practice:

- Does importing your actual SIMC export select the expected configuration?
- Are there unreasonable ability priorities, DoT maintenance decisions, or Insanity handling?
- Does Hold Burst behave as expected when saving cooldowns for a raid phase or target?

When reporting a problem, include your talent setup, the approximate time, and the relevant recommendation log. Remove any personal information you do not want to share.

### Download and installation

First-time users need to install both the **desktop app** and the **game addon** separately.

1. Open the [download page](https://github.com/muttsf/RyoGeese/releases). Under **Assets**, download the installer whose name ends in **`x64-Setup.exe`**, run it, and finish installation. Players do not need the source ZIP.
2. Follow the [Dash installation guide](https://github.com/muttsf/RyoGeese-Dash#english) to put the addon in your game's `Interface/AddOns` directory.
3. Launch the game, enable Dash, and keep its entire panel visible. Open RyoGeese, or double-click **`点我启动.exe`** in the application's installation folder.

The app installer does not contain the addon; they are updated separately. The current test release is **not digitally signed**. Download it from this project's release page, which also provides the corresponding source and `SHA256SUMS.txt`.

### First-time setup

Follow the four cards from top to bottom. Completing a step unlocks the next one. The button names below match the current Chinese interface.

| Step | Action |
| --- | --- |
| **1 · Import SIMC** | In the game, use the SimulationCraft addon and enter `/simc`. Copy your current character's full export. In RyoGeese, click “导入SIMC”, paste it, and confirm. The app checks your specialization, talents, and equipment and loads a supported rotation. |
| **2 · Locate Dash** | Keep the game and entire Dash panel visible, click “定位插件”, and wait for completion. |
| **3 · Set ability keys** | Click “设置技能按键” and enter the keys you actually use, such as `1`, `E`, or `Shift+1`. You may fill in some keys or leave them all blank; opening the settings is enough to continue. |
| **4 · Start** | Check “确认配置，准备开始”, then click “开始推荐”. Allow time for the initial load; the recommendation window appears when ready. |

Exporting SIMC requires the separate [SimulationCraft game addon](https://github.com/simulationcraft/simc-addon). RyoGeese saves your previous export and keybinds; use “载入上次” to load them again. Import a fresh export after changing your talents or equipment.

### Recommendation window

- **Ability and keybind**: Shows the most recently received recommendation. A blank keybind is displayed as “鼠标点击” (“Mouse click”).
- **Hold Burst / Resume Burst**: Use “暂缓爆发” or “恢复爆发” to change burst recommendations. The current state appears in the upper right.
- **Minimal mode**: Click “极简” to show mainly the keybind. Double-click the small window or press `Esc` to return to the standard view.
- **Relocate**: After moving Dash or changing its size or font size, click “重新定位”.
- **Exit**: Click “退出” to close the recommendation window and end the current recommendation session.

**Current behavior:** A capture is scheduled every **500 milliseconds**, recognition runs serially, and the current ability suggestion is displayed. A future version may reduce the capture interval to around **300 milliseconds** to reduce idle waiting after players use cast-time abilities. This is a future optimization plan. Actual capture intervals and processing time depend on system load. The current release shows only the first recommendation, without next-ability prediction.

### Optional ability icons

The first release does not bundle game ability images or internet audio clips. Without an icon pack, ability names and keybinds still work, while the icon area stays blank.

If you have a compatible icon pack, click **“导入图标包”** on the main page and select the ZIP. **No extraction or individual icon setup is required.** Import the new pack again when updating it.

A pack may contain icons for multiple specializations; that does not mean their rotations are supported. See [ICON_IMPORT.txt](ICON_IMPORT.txt) for the pack format in Chinese.

### Hardware and game requirements

| Item | Current scope |
| --- | --- |
| Game | **Retail 12.1.5**, level 90, with supported Shadow Priest talents. Compatibility is checked during import. |
| Tested system and GPU | **Windows 11 + NVIDIA RTX 5080**. |
| Other NVIDIA GPUs | **RTX 30 series and newer are theoretical compatibility targets**, without testing on every model. |
| AMD | AMD CPUs can be used. **AMD GPUs are not currently supported.** |
| Memory and runtime environment | **There is no real-machine compatibility guarantee for 8GB RAM configurations.** The GPU driver and Microsoft Visual C++ x64 runtime must meet the application's requirements. |

**Author's note:** “I will try to add AMD GPU support, but I cannot guarantee it yet and do not have an AMD card for testing. This is my first software project, and I used mature CUDA libraries and tools. I will look for ways to support AMD in the future, and I hereby promise that the Sapphire 7900 XTX is the most beautiful graphics card in the world.”

### Frequently asked questions

**Why does a fresh installation still show my previous SIMC export?**<br>
Character data and keybinds are stored in your local user directory and intentionally retained during uninstallation. The public installer does not contain the author's private SIMC export, keybinds, or logs.

**What if locating Dash fails, or I move the panel?**<br>
Keep the game window and the entire Dash panel visible, then use “定位插件” or “重新定位”. Locate it again after changing its position, size, or font size. See [runtime boundaries](app/运行边界说明.txt) for details in Chinese.

**How are rotations updated? Do I need to import one myself?**<br>
Maintainers review game patches and SimulationCraft changes, validate updates, and release them with the software. Download the new app version to receive them. You do not import rotation files, and the current release does not update rotations automatically online.

**How do I report a problem?**<br>
Click “打开日志” on the main page and find the corresponding error or recommendation log. Open an [issue](https://github.com/muttsf/RyoGeese/issues) describing what happened, your app version, GPU model, and the time. Check logs for information you do not want to make public before uploading them.

Logs are rotated, and old closed log files are cleaned up with a target of approximately **200MiB**. A cleanup failure will not block recommendations to enforce that target.

<details>
<summary>Local data locations</summary>

- SIMC and keybinds: `%LOCALAPPDATA%\AiHekili\startup\current.json` (the legacy path is retained for compatibility).
- Error and recommendation logs: `%LOCALAPPDATA%\RyoGeese\logs`.
- Imported icons: `%LOCALAPPDATA%\RyoGeese\icons`.

Exit both the main and recommendation windows before updating or uninstalling. The game stores addon settings separately.

</details>

### Development and licensing

Issues and pull requests are welcome. Keep changes focused and explain the reason and validation. Changes affecting recommendations, recognition, or installation need appropriate checks.

- [Build instructions](BUILDING_PORTABLE.txt): Prepare runtime dependencies, assemble the app, and build the installer. You currently need to supply dependencies matching the manifest; there is no one-click build with automatic dependency downloads.
- [Maintenance workflow](MAINTENANCE.txt): Review game patches and SIMC, validate changes, and release rotations.
- `app/`: Desktop UI, built-in rotation, visual recognition supervision, and reference data.
- `native/`: Independent GPU reader source. External runtime dependency hashes are listed in `DEPENDENCIES.json`.

Project-owned source is licensed under **GPL-3.0-only**. The project-owned GPU reader has an additional permission for NVIDIA and Microsoft runtimes. Third-party components retain their own licenses; see [LICENSE](LICENSE), [licensing scope](LICENSING.md), and [third-party notices](app/notices/).
