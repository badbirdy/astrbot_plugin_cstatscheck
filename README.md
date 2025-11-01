# astrbot_plugin_cstatscheck

# ✨Astrbot cs 5e平台战绩查询插件

[![License](https://img.shields.io/badge/License-AGPL--3.0-blue.svg)](https://www.gnu.org/licenses/agpl-3.0.html)
[![Python 3.8+](https://img.shields.io/badge/Python-3.8%2B-blue.svg)](https://www.python.org/)
[![AstrBot](https://img.shields.io/badge/AstrBot-3.4%2B-orange.svg)](https://github.com/Soulter/AstrBot)

一个基于 Astrbot 的cs 5e平台战绩查询插件，支持：

- 玩家战绩查询
- LLM 调用，大模型会怎么看待你的战绩呢

## ⌨️ 怎么使用

### 指令式

| 功能        | 命令格式                                     | 参数说明                                | 备注            | 别名     |
|-----------|------------------------------------------|-------------------------------------|---------------|--------|
| **账号绑定**  | `/bind [5e_playername]`                    | `5e_playername`: 5e账号名                    | -             | `/绑定`, `/添加`, `/绑定用户`, `/添加用户`  |
| **查询战绩**  | `/match [@qq名] [match_round]`        | `@qq名`: 艾特某个qq群聊用户 <br>`match_round`: 倒数第几把游戏    | -match_round 默认为1，即倒数第一把，仅支持查询最近5把             | `/战绩`, `/查询战绩`      |
| **帮助**    | `/cs_help`                           | -                                   | -             | -      |

💡 提示

**实际输入命令中不需要[]**

**命令示例**

- `全参`:/match @群昵称 3
- `查询已绑定的群友战绩`:/match @群昵称
- `无参`:/match

## 👍致谢

### 💻 开源项目

- [astrbot_plugin_battlefield_tool](https://github.com/SHOOTING-STAR-C/astrbot_plugin_battlefield_tool/tree/master?tab=readme-ov-file) - 参考了其代码框架设计
- [AstrBot](https://github.com/AstrBotDevs/AstrBot) - 优秀的机器人框架

🙌 衷心感谢所有使用者和贡献者的支持！您的反馈和建议是我们持续改进的动力！

## 🤝 参与贡献

欢迎任何形式的贡献！以下是标准贡献流程：

1. **Fork 仓库** - 点击右上角 Fork 按钮创建您的副本
2. **创建分支** - 基于开发分支创建特性分支：
   ```bash
   git checkout -b feature/your-feature-name
   ```
3. **提交修改** - 编写清晰的提交信息：
   ```bash
   git commit -m "feat: 添加新功能" -m "详细描述..."
   ```
4. **推送更改** - 将分支推送到您的远程仓库：
   ```bash
   git push origin feature/your-feature-name
   ```
5. **发起 PR** - 在 GitHub 上创建 Pull Request 到原仓库的 `main` 分支

## 📜 开源协议

本项目采用 [GNU Affero General Public License v3.0](LICENSE)
