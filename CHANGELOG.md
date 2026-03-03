# 更新日志

本文档用于记录 `astrbot_plugin_cstatscheck` 的版本变更。

## [v2.0.0] - 2026-03-03

本版本为从 `v1.2.1` 升级到 `v2.0.0` 的大版本更新，包含平台能力扩展、存储层重构与指令行为增强。

### 新增

- 新增多平台逻辑模块，按平台拆分实现:
  - `core/platforms/fivee_logic.py`
  - `core/platforms/pw_logic.py`
  - `core/platforms/mm_logic.py`
  - `core/platforms/__init__.py`
- 新增 AI 评价模块 `core/ai_logic.py`，将 LLM 调用与评价输入构建逻辑独立封装。
- 新增 SQLite 存储初始化与绑定写入能力，支持按 `qq_id + platform` 维度维护绑定数据。

### 变更

- 插件定位从「仅 5e」升级为「全平台战绩查询」，并更新版本到 `v2.0.0`:
  - `main.py` 插件注册信息更新
  - `metadata.yaml` 版本号更新
  - `README.md` 功能描述更新
- `bind` 与 `match` 指令扩展为平台感知参数:
  - `bind` 支持 `5e/pw`
  - `match` 支持 `5e/pw/mm`
  - `mm` 查询复用 `pw` 绑定信息
- 查询输出支持按平台补充信息（如 `pw/mm` 的比赛类型），并统一通过引用回复链返回关键提示。
- LLM 提示词模板增强，补充输出示例与错误示例，提升风格稳定性。

### 重构

- `core/plugin_logic.py` 大幅重构:
  - 引入平台路由与平台别名归一化
  - 将平台相关请求/解析下沉至 `core/platforms/*`
  - 抽离 AI 能力到 `core/ai_logic.py`
  - 增加旧 `user_data.json` 到 `user_data.db` 的迁移流程
- 数据模型升级:
  - `models/player_data.py` 引入 `platform` 字段并统一类型标注
  - `models/match_data.py` 增加 `match_type` 字段并完善默认值

### 修复

- 优化 `@` 提及后的目标用户解析与查询流程，减少群聊场景下查错对象的问题。
- 优化未绑定、缺失平台绑定、网络失败等场景的错误提示与兜底处理。
- 优化场次提取与比赛数据解析链路，提升多平台查询稳定性。

### 文档与工程化

- `README.md` 同步更新全平台用法、参数说明与示例命令。
- `.gitignore` 调整忽略项（如 `api_response`、`scripts`）。
- 删除 `pyproject.toml`，移除旧的本地项目配置文件。
- 新增 `CHANGELOG.md`，用于后续版本持续记录。

## [v1.2.1]

### 说明

- `v2.0.0` 之前的稳定版本基线。
