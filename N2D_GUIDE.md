# novel2drama — 短剧分镜工作台（AI 编码 agent 项目指南）

本仓库是 novel2drama 后端 + 前端本体（FastAPI + Jinja + SQLite）。你的任务是通过
`n2d` 命令行工具读写后端数据，帮助用户修改剧情 / 分镜 / 资产等。

## 工作方式约定

1. **一切数据操作走 `n2d` CLI**，不要直接改 SQLite 文件或后端源码里的数据。
   `n2d` 已在 PATH（`/usr/local/bin/n2d`），直连后端 `http://127.0.0.1:8010`。
2. **先读后写**：修改前先用 `n2d` 列出 / 读出目标（用其 id 前缀），再定位精确资源。
3. `n2d` 默认人类可读输出；加 `-j/--json` 输出原始 JSON，便于程序化解析。
4. 修改剧情时保持台词、节奏与既有文风一致；只做用户要求的最小改动，不擅自扩写。
5. 涉及数据变更的命令会被要求「行为确认」——用自然语言描述你要做什么，别只贴命令串。

## n2d 常用命令速查

```bash
# 浏览（读）
n2d projects
n2d project <id>
n2d episodes <project_id>
n2d novels <project_id>
n2d novel <version_id>
n2d chapters <version_id>
n2d chapter <chapter_id>
n2d segments <project_id>
n2d seg <project_id> <segment_id>
n2d beats <segment_id>
n2d assets <project_id>
n2d jobs <project_id>
n2d exports <project_id>

# 写（会触发行为确认）
n2d novel new <project_id> <标题> <文件或文本>
n2d novel activate <project_id> <version_id>
n2d chapter parse <version_id>
n2d chapter edit <cid> --title "标题" --drop/--include
n2d seg new <project_id> --no 1 --summary "摘要" [--start ...] [--end ...]
n2d seg edit <sid> --summary "改后摘要" [--start ...] [--end ...]
n2d seg rm <sid>
n2d beat new <sid> [--start ms] [--end ms] [--shot 景别] [--action 人物动作] ...
n2d beat edit <bid> --summary ... / --action ... / --camera ...
n2d beat rm <bid>
n2d asset new <project_id> --type character|scene --name 名称 [--desc ...]
n2d asset confirm <asset_id>
n2d episode new <project_id>
n2d kframe generate <segment_id>          # 生成段首图
n2d keyframe select <sid> --keyframe <kid> # 选定段首图
```

> 版本/分段/分镜大改建议走「新版本 + 激活」而非直接改写原稿，保留回退。
