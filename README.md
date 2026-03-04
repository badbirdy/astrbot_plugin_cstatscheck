# astrbot_plugin_csstats

# ✨Astrbot cs 全平台战绩查询插件

[![License](https://img.shields.io/badge/License-AGPL--3.0-blue.svg)](https://www.gnu.org/licenses/agpl-3.0.html)
[![Python 3.8+](https://img.shields.io/badge/Python-3.8%2B-blue.svg)](https://www.python.org/)
[![AstrBot](https://img.shields.io/badge/AstrBot-3.4%2B-orange.svg)](https://github.com/Soulter/AstrBot)

一个基于 Astrbot 的 cs 全平台战绩查询插件，支持：

- 完美，5e，官匹平台的玩家战绩查询
- LLM 评价调用：采用短评加长评形式，并综合队友和对手战绩。大模型会怎么看待你的战绩呢
- 组排玩家检测：从已绑定玩家的数据库中找出与你组排的玩家并在群里艾特出那个最菜的队友（小心是你自己！）

## 怎么使用

### 指令式

| 功能        | 命令格式                                     | 参数说明                                | 备注            | 别名     |
|-----------|------------------------------------------|-------------------------------------|---------------|--------|
| **账号绑定**  | `/bind [platform] [name]`                    | `platform`: 5e/pw(可选，默认5e) <br>`name`: 5e平台是游戏名称，完美平台是完美app的用户名                    | *该命令仅用于将游戏ID绑定至发送者QQ号*             | `/绑定`, `/添加`, `/绑定用户`, `/添加用户`  |
| **查询战绩**  | `/match [platform] [@qq名] [match_round]`        | `platform`: 5e/pw/mm(可选，默认5e) <br>`@qq名`: 艾特某个qq群聊用户 <br>`match_round`: 倒数第几把游戏    | -match_round 默认为1，即倒数第一把，5e平台支持查询最近5把，完美和官匹支持查询最近10把<br>-若艾特的是bot，则查询命令发送者自己的战绩<br>-mm 查询复用 pw 绑定信息，请先 `/bind pw`             | `/战绩`, `/查询战绩`      |
| **帮助**    | `/cs_help`                           | -                                   | -             | -      |

### 提示

1. **实际输入命令中不需要[]**
2. **绑定完美平台时使用的是手机完美世界app客户端的用户名，不是完美游戏名称！**
3. **绑定5e平台时使用的是5e游戏名称**
4. **绑定完美平台成功后即可查询完美战绩和官匹战绩**

**命令示例**

- `绑定`:/bind 5e ExamplePlayer
- `绑定`:/bind pw ExampleUser
- `查询自己第2把`:/match 5e 2
- `查询已绑定的群友战绩`:/match pw @群昵称 3
- `查询官匹战绩`:/match mm @群昵称

## 致谢

### 开源项目

- [astrbot_plugin_battlefield_tool](https://github.com/SHOOTING-STAR-C/astrbot_plugin_battlefield_tool/tree/master?tab=readme-ov-file) - 参考了其代码框架设计
- [AstrBot](https://github.com/AstrBotDevs/AstrBot) - 优秀的机器人框架

### 注意

- **本项目仅供技术研究、学习交流及玩家查询本人或他人公开的战绩数据使用！**
- **所有代码都是开源且透明的，任何人均可查看，程序不会保存或滥用任何用户的个人信息**
- **衷心感谢所有使用者和贡献者的支持！您的反馈和建议是我们持续改进的动力！**

## 参与贡献

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

## 开源协议

本项目采用 [GNU Affero General Public License v3.0](LICENSE)
