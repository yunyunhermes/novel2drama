# novel2drama

小说 → 单集 AI 漫剧工作台。把一篇小说原文经人机协同的分镜化流程，转化为一段由多个 **15 秒段**顺序拼接而成的单集 AI 漫剧（片长自制，约 2 分钟 ≈ 8 段、3 分钟 ≈ 12 段）。

[![License](https://img.shields.io/badge/License-MIT-blue.svg)](LICENSE)

- 后端：FastAPI + SQLite
- 前端：Jinja2 模板 + 原生 JS（无前端框架）
- 生成：ComfyUI 驱动 Z-Image / H3，GPU 单 worker 串行队列
- LLM：分镜生成 / 镜头补全 / 剧情压缩 / H3 prompt 汇总（走 OpenAI 兼容网关，不占本地显存）
- 拼接：ffmpeg

## 工作流

```
小说原文
  → 人机协同分镜编辑
  → 分镜确认
  → 角色/场景资产确认（双级确认：抽卡选定 + 高质量预览人工确认）
  → Z-Image 段首关键帧
  → 人工复核
  → H3 15s 段
  → 人工复核
  → 多段拼接
  → 单集导出
```

项目状态机：`draft → novel_ready → storyboard → assets → keyframes → h3 → export`

## 关键概念

| 概念 | 说明 |
|------|------|
| **分镜 (Storyboard)** | 不是逐镜头生成视频，而是规划 15s 段内部的镜头节奏（1–3s 一个节拍），汇总成一段连续时序 prompt 供 H3 使用。 |
| **Z-Image** | 角色/场景资产图 + 15s 段首关键帧。 |
| **H3** | 段首图 + 15s 连续 prompt → 生成一段 15s 视频。 |
| **单集 (Episode)** | 多个 15s 段顺序拼接而成。一个项目可含多集，共享全局资产，各集持独立分镜/版本/任务。 |

## 页面

项目列表 / 小说编辑 / 分镜协同（左原文 · 中段列表 · 右段详情+节拍）/ 资产复核 / 段首图复核 / 15s 段复核 / 成片导出。

## 快速开始

前置：Python 3.11+。

```bash
# 1. 安装依赖
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt

# 2. 初始化数据库（幂等，即可选）
python scripts/init_db.py

# 3. 启动开发服务
python -m uvicorn app.main:app --port 8010
```

访问 <http://127.0.0.1:8010>。数据库为 SQLite（默认 `data/novel2drama.db`，可用环境变量 `N2D_DB_PATH` 覆盖），启动时 `schema.migrate_episodes` 幂等迁移。

> 生成类功能（Z-Image / H3）需连接 GPU 侧 ComfyUI 与生成网关；本地默认仅管理 Web + 编排。

## n2d CLI

`n2d` 是直连后端 REST API 的命令行工具，方便脚本 / AI 编码 agent 直接调用后端全流程，无需访问 Web UI。

```bash
# 软链（安装一次）
ln -sf /path/to/repo/cli/n2d /usr/local/bin/n2d

# 指定后端地址（默认 http://127.0.0.1:8010）
export N2D_HOST=http://<host>:<port>
export N2D_AUTH=admin:PASSWORD        # 如有 basic auth

# 浏览
n2d projects
n2d project <id>
n2d episodes <project_id>
n2d novels <project_id>
n2d segments <project_id>
n2d assets <project_id>
n2d jobs <project_id>

# 写操作（会触发行为确认）
n2d novel new <project_id> <标题> <文件或文本>
n2d chapter parse <version_id>
n2d seg new <project_id> --no 1 --summary "主角推门" --start "门口" --end "屋内"
n2d seg edit <sid> --summary "改后摘要"
n2d beat new <sid> --start 0 --end 3000 --shot "中景" --camera "缓慢推近"
n2d beat edit <bid> --end 3500 --camera "慢摇"
n2d asset confirm <asset_id>
n2d keyframe select <sid> --keyframe <kid>

# JSON 输出（AI 友好）
n2d -j chapters <version_id>
```

完整命令总览见 `cli/README.md`。

## AI agent 接入（opencode ACP）

后端内置 opencode (Agent Client Protocol) agent 桥接：AI 编码 agent 可通过 ACP 连接后端，以 `n2d` CLI 作为工具读写数据，并通过「行为卡片」机制对写操作做人工批准/拒绝。相关说明见 `N2D_GUIDE.md`。

## 目录结构

```
app/
  main.py          # FastAPI 入口、路由注册、/files 文件服务
  config.py        # 路径/数据目录
  db.py  models.py schema.py
  routers/         # projects/novels/storyboard/assets/generation/review/export/episodes/agent
  services/        # llm/gateway/prompt/storage/ffmpeg/agent/acp_bridge/n2d_cards/system_status/config/...
  workers/         # gpu_worker.py
cli/n2d.py, n2d    # 直连后端 REST 的 CLI
templates/         # base + 各页面模板
static/            # app.css/app.js + agent.css/agent.js
data/              # 项目数据 + SQLite db
scripts/           # init_db.py run_dev.sh
docs/              # 需求与架构 / 开发进度 / 变更需求
```

## 部署

宿主机用于开发，运行部署到带 GPU 的服务器（rsync 同步 + systemd 管理 `novel2drama.service` 与 `novel2drama-worker.service`）。前端静态资源通过 `?v=` 版本串防止浏览器缓存，修改后记得递增。

## 文件服务

`GET /files/{project_id}/{path}` 提供项目文件（图片/视频/导出物）下载，已做目录穿越防护。

## 许可

本项目采用 [MIT 许可证](LICENSE) 开源。Copyright (c) 2026 yunyunhermes。
