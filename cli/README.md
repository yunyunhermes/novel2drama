# n2d — novel2drama 后端 CLI

直连 novel2drama 后端 REST API 的命令行工具，方便 AI / 脚本直接调用后端全流程，无需访问 Web UI。

## 安装

```bash
ln -sf /root/projects/novel2drama/cli/n2d /usr/local/bin/n2d
```

## 配置

通过环境变量指定后端地址与认证：

```bash
export N2D_HOST=http://192.168.1.200:8080   # 或 GPU 服务器内网 / 公网地址
export N2D_AUTH=admin:PASSWORD             # 如有 basic auth
```

默认 `http://127.0.0.1:8010`。

## 快速上手

```bash
# 列出项目
n2d projects

# 项目详情
n2d project detail <project_id>

# 创建小说版本（从文件读原文）
n2d novel new <project_id> "标题" /path/to/novel.txt

# 触发章节解析
n2d chapter parse <version_id>

# 章节列表
n2d chapters <version_id>

# 段落列表 / 创建段
n2d segments <project_id>
n2d seg new <project_id> --no 1 --summary "主角推门" --start "门口" --end "屋内"

# 段详情(含节拍) / 节拍列表
n2d seg detail <project_id> <segment_id>
n2d beats <segment_id>

# 创建/编辑节拍
n2d beat new <segment_id> --start 0 --end 3000 --shot "中景" --camera "缓慢推近" --action "主角抬头" --emotion "紧张"
n2d beat edit <beat_id> --end 3500 --camera "慢摇"

# 构建段首图/H3 prompt(写回后端)
n2d builds <segment_id>

# 任务列表 / 详情
n2d jobs <project_id>
n2d job <job_id>

# 导出列表
n2d exports <project_id>
```

## AI 友好模式（JSON 输出）

```bash
n2d -j chapters <version_id>     # 输出原始 JSON，便于程序化解析
```

## 命令总览

```
projects             listing
project              detail / new / rm
novels               listing
novel                detail / new / activate
chapters             listing
chapter              detail / parse / edit(--title --drop --include) / rm
segments             listing
seg                  detail / new(--no --summary --start --end) / edit / rm
beats                listing
beat                 new / edit / rm
assets               listing
asset                new(--type --name --appearance ...) / confirm
builds               build keyframe/h3 prompt
kframe               view / select / generate
jobs                 listing
job                  detail
exports              listing
```
