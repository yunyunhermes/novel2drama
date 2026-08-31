#!/usr/bin/env python3
"""n2d — novel2drama 后端 CLI 工具。

直连 novel2drama 后端 REST API，方便 AI / 脚本直接调用后端全流程。

用法:
  n2d <command> [options]

全局选项:
  --host <base_url>     后端地址 (默认 $N2D_HOST 或 http://127.0.0.1:8010)
  --auth <user:pass>    基础认证 (默认 $N2D_AUTH)
  -j, --json            输出原始 JSON (便于程序化解析，默认关闭)
  --timeout <sec>       HTTP 超时秒数 (默认 30)

命令:
  projects                列出项目
  project <id>           项目详情
  project new <name> ... 创建项目
  project rm <id>        删除项目
  novels <proj>          项目的小说版本列表
  novel <vid>            小说版本详情(含原文)
  novel new <proj> <标题> <文件或文本>   创建小说版本
  novel activate <proj> <vid>            激活版本
  chapters <vid>         版本章节列表
  chapter <cid>          单章详情
  chapter parse <vid>    触发章节解析
  chapter edit <cid> --title <t> --drop   编辑章节
  chapter rm <cid>       删除章节
  segments <proj>        段落列表
  seg <sid>              段落详情+节拍
  seg new <proj> --no <n> --summary <s>    创建段
  seg edit <sid> --summary <s> --start <t> --end <t>   编辑段
  seg rm <sid>           删除段
  beats <sid>            段内节拍
  beat new <sid> [--start ms] [--end ms] [--field v] ...  创建节拍
  beat edit <bid> [--field v] ...          编辑节拍
  beat rm <bid>          删除节拍
  assets <proj>          资产列表
  asset new <proj> --type <t> --name <n> [..]   创建资产
  asset confirm <aid>    确认资产
  builds <sid>           build keyframe/h3 prompt
  kframe <sid>           查看/选定段首图
  jobs <proj>            项目任务列表
  job <jid>              任务详情
  exports <proj>         导出列表

环境变量:
  N2D_HOST   后端基础地址
  N2D_AUTH   user:pass 基础认证
"""
import sys
import os
import json
import base64
import argparse
import urllib.request
import urllib.error

DEFAULT_HOST = os.environ.get("N2D_HOST", "http://127.0.0.1:8010")
AUTH_ENV = os.environ.get("N2D_AUTH")


# ---------- HTTP 层 ----------
def api(host, auth, path, method="GET", body=None, timeout=30):
    url = host.rstrip("/") + path
    data = json.dumps(body, ensure_ascii=False).encode() if body is not None else None
    req = urllib.request.Request(url, data=data, method=method)
    req.add_header("Content-Type", "application/json")
    if auth:
        token = base64.b64encode(auth.encode()).decode()
        req.add_header("Authorization", "Basic " + token)
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        raw = e.read().decode("utf-8", "replace")
        try:
            r = json.loads(raw)
            # FastAPI 默认错误格式 {"detail": "..."}
            if isinstance(r, dict) and "detail" in r and "success" not in r:
                return {"success": False, "error": {"code": f"HTTP_{e.code}", "message": str(r["detail"])}}
            return r
        except Exception:
            return {"success": False, "error": {"code": f"HTTP_{e.code}", "message": raw[:500]}}
    except Exception as e:
        return {"success": False, "error": {"code": "NETWORK", "message": str(e)}}


def fail(resp):
    if not resp.get("success"):
        err = resp.get("error", {})
        return f"失败: [{err.get('code','?')}] {err.get('message','?')}"
    return None


def out(resp, json_mode, quiet=False):
    """统一输出: 失败打印错误到 stderr 返回 None。
    成功: json_mode 时打印原始 JSON; 否则返回 data 由 cmd 负责人类可读格式化。"""
    if fail(resp):
        print(fail(resp), file=sys.stderr)
        return None
    data = resp.get("data")
    if json_mode:
        print(json.dumps(data, ensure_ascii=False, indent=2))
    return data


def esc(v):
    if v is None:
        return ""
    return str(v)


# ---------- 字段解析辅助 ----------
def _field_map():
    """各实体可编辑/可创建的字段名。key = 命令行 flag 名(去掉 --), value = 后端字段名。"""
    return {
        "seg": {
            "no": "sort_order", "summary": "summary",
            "start": "start_transition", "end": "end_transition",
        },
        "beat": {
            "no": "sort_order", "start": "start_ms", "end": "end_ms",
            "shot": "shot_size", "camera": "camera_movement",
            "action": "character_action", "scene": "scene_change",
            "light": "lighting", "comp": "composition",
            "style": "style", "emotion": "emotion", "transition": "transition",
        },
        "asset": {
            "name": "name", "desc": "description", "type": "asset_type",
            "appearance": "appearance_anchor", "costume": "costume_anchor",
            "temperament": "temperament_anchor", "time": "time",
            "weather": "weather", "lighting": "lighting",
            "color": "color_tendency", "negative": "negative_prompt",
        },
    }


# ---------- 各子命令实现 ----------
def cmd_projects(args, c):
    resp = api(c.host, c.auth, "/api/v1/projects", timeout=c.timeout)
    data = out(resp, c.json)
    if data:
        for p in data:
            print(f"{p['id'][:8]}  {esc(p.get('name'))}  [{esc(p.get('status'))}]  {esc(p.get('target_duration_seconds',''))}s  {esc(p.get('updated_at',''))}")


def cmd_create_project(args, c):
    body = {"name": args.name}
    if args.desc: body["description"] = args.desc
    if args.duration: body["target_duration_seconds"] = args.duration
    if args.style: body["style_prompt"] = args.style
    resp = api(c.host, c.auth, "/api/v1/projects", "POST", body, c.timeout)
    data = out(resp, c.json)
    if data:
        print(f"创建成功 project_id={data.get('project_id')}")


def cmd_delete_project(args, c):
    resp = api(c.host, c.auth, f"/api/v1/projects/{args.project_id}", "DELETE", timeout=c.timeout)
    data = out(resp, c.json)
    if data:
        print("已删除")


def cmd_project_detail(args, c):
    resp = api(c.host, c.auth, f"/api/v1/projects/{args.project_id}", timeout=c.timeout)
    data = out(resp, c.json)
    if data:
        print(f"名称: {data.get('name')}  状态: {data.get('status')}")
        print(f"目标时长: {data.get('target_duration_seconds')}s  风格: {esc(data.get('style_prompt'))}")
        print(f"当前版本: {data.get('current_novel_version_id')}")


def cmd_list_episodes(args, c):
    resp = api(c.host, c.auth, f"/api/v1/projects/{args.project_id}/episodes", timeout=c.timeout)
    data = out(resp, c.json)
    if data:
        for e in data:
            print(f"{e['id'][:8]}  第{e.get('episode_no')}集  [{esc(e.get('title'))}]  [{esc(e.get('status'))}]  {esc(e.get('updated_at',''))}")


def cmd_create_episode(args, c):
    resp = api(c.host, c.auth, f"/api/v1/projects/{args.project_id}/episodes", "POST", timeout=c.timeout)
    data = out(resp, c.json)
    if data:
        print(f"创建成功 episode_id={data.get('episode_id')}  第{data.get('episode_no')}集")


def cmd_list_novels(args, c):
    resp = api(c.host, c.auth, f"/api/v1/projects/{args.project_id}/novel-versions", timeout=c.timeout)
    data = out(resp, c.json)
    if data:
        for v in data:
            print(f"{v['id'][:8]}  {esc(v.get('title'))}  v{v.get('version_no')}  {'[active]' if v.get('is_active') else ''}  {v.get('text_length',0)}字  {esc(v.get('created_at',''))}")


def cmd_novel_detail(args, c):
    resp = api(c.host, c.auth, f"/api/v1/novel-versions/{args.version_id}", timeout=c.timeout)
    data = out(resp, c.json)
    if data:
        print(f"标题: {data.get('title')}  v{data.get('version_no')}  active={data.get('is_active')}")
        print("原文:")
        print(data.get("source_text") or "")


def cmd_create_novel(args, c):
    # 从文件或文本读取
    src = args.source
    if os.path.isfile(src):
        with open(src, "r", encoding="utf-8") as f:
            text = f.read()
    else:
        text = src
    body = {"title": args.title, "source_text": text}
    resp = api(c.host, c.auth, f"/api/v1/projects/{args.project_id}/novel-versions", "POST", body, c.timeout)
    data = out(resp, c.json)
    if data:
        print(f"版本创建成功 version_id={data.get('version_id')} active={data.get('is_active')}")
        return data.get("version_id")


def cmd_activate_novel(args, c):
    resp = api(c.host, c.auth, f"/api/v1/projects/{args.project_id}/novel-versions/{args.version_id}/activate",
               "POST", timeout=c.timeout)
    data = out(resp, c.json)
    if data:
        print("版本已激活")


def cmd_list_chapters(args, c):
    resp = api(c.host, c.auth, f"/api/v1/novel-versions/{args.version_id}/chapters", timeout=c.timeout)
    data = out(resp, c.json)
    if data:
        for ch in data:
            print(f"{ch['id'][:8]}  {esc(ch.get('title'))}  #{ch.get('sort_order')}  {'[in]' if ch.get('included') else '[x]'}  {ch.get('text_length',0)}字  {esc(ch.get('content_preview',''))[:40]}")


def cmd_chapter_detail(args, c):
    resp = api(c.host, c.auth, f"/api/v1/chapters/{args.chapter_id}", timeout=c.timeout)
    data = out(resp, c.json)
    if data:
        print(f"标题: {data.get('title')}  参与: {data.get('included')}")
        print(data.get("content") or "")


def cmd_parse_chapters(args, c):
    resp = api(c.host, c.auth, f"/api/v1/novel-versions/{args.version_id}/parse-chapters", "POST", timeout=c.timeout)
    data = out(resp, c.json)
    if data:
        print(f"解析完成，共 {data.get('parsed')} 章")


def cmd_edit_chapter(args, c):
    body = {}
    if args.title is not None: body["title"] = args.title
    if args.drop: body["included"] = False
    if args.include: body["included"] = True
    if not body:
        print("未指定任何修改 (--title / --drop / --include)", file=sys.stderr); return
    resp = api(c.host, c.auth, f"/api/v1/chapters/{args.chapter_id}", "PATCH", body, c.timeout)
    data = out(resp, c.json)
    if data:
        print("章节已更新")


def cmd_delete_chapter(args, c):
    resp = api(c.host, c.auth, f"/api/v1/chapters/{args.chapter_id}", "DELETE", timeout=c.timeout)
    data = out(resp, c.json)
    if data:
        print("章节已删除")


def cmd_list_segments(args, c):
    resp = api(c.host, c.auth, f"/api/v1/projects/{args.project_id}/segments", timeout=c.timeout)
    data = out(resp, c.json)
    if data:
        for s in data:
            print(f"{s['id'][:8]}  第{s.get('sort_order')}段 [{esc(s.get('status'))}]  {esc(s.get('summary',''))[:40]}")


def cmd_segment_detail(args, c):
    resp = api(c.host, c.auth, f"/api/v1/projects/{args.project_id}/segments", timeout=c.timeout)
    segs = out(resp, c.json)
    if not segs: return
    s = next((x for x in segs if x.get("id") == args.segment_id), None)
    if not s:
        print("段未找到", file=sys.stderr); return
    print(f"### 第{s.get('sort_order')}段 [{s.get('status')}]")
    print(f"摘要: {esc(s.get('summary'))}")
    print(f"首接: {esc(s.get('start_transition'))}  尾接: {esc(s.get('end_transition'))}")
    # 节拍
    bres = api(c.host, c.auth, f"/api/v1/segments/{args.segment_id}/beats", timeout=c.timeout)
    beats = out(bres, c.json, quiet=True)
    if beats:
        print("--- 节拍 ---")
        for b in beats:
            print(f"  {b.get('start_ms')}ms-{b.get('end_ms')}ms [{esc(b.get('shot_size'))}] {esc(b.get('character_action',''))[:40]} 运镜:{esc(b.get('camera_movement'))}")


def cmd_create_segment(args, c):
    body = {"sort_order": args.no, "summary": args.summary or ""}
    if args.start: body["start_transition"] = args.start
    if args.end: body["end_transition"] = args.end
    resp = api(c.host, c.auth, f"/api/v1/projects/{args.project_id}/segments", "POST", body, c.timeout)
    data = out(resp, c.json)
    if data:
        print(f"段创建成功 segment_id={data.get('segment_id')}")
        return data.get("segment_id")


def cmd_edit_segment(args, c):
    body = {}
    if args.summary is not None: body["summary"] = args.summary
    if args.start is not None: body["start_transition"] = args.start
    if args.end is not None: body["end_transition"] = args.end
    if not body:
        print("未指定任何修改", file=sys.stderr); return
    resp = api(c.host, c.auth, f"/api/v1/projects/{args.project_id}/segments/{args.segment_id}", "PATCH", body, c.timeout)
    data = out(resp, c.json)
    if data:
        print("段已更新")


def cmd_delete_segment(args, c):
    resp = api(c.host, c.auth, f"/api/v1/projects/{args.project_id}/segments/{args.segment_id}", "DELETE", timeout=c.timeout)
    data = out(resp, c.json)
    if data:
        print("段已删除")


def cmd_list_beats(args, c):
    resp = api(c.host, c.auth, f"/api/v1/segments/{args.segment_id}/beats", timeout=c.timeout)
    data = out(resp, c.json)
    if data:
        for b in data:
            print(f"{b['id'][:8]}  {b.get('start_ms')}-{b.get('end_ms')}ms [{esc(b.get('shot_size'))}] {esc(b.get('character_action',''))[:40]}")


def cmd_create_beat(args, c):
    fm = _field_map()["beat"]
    body = {}
    for flag, field in fm.items():
        val = getattr(args, flag, None)
        if val is not None:
            body[field] = int(val) if field in ("start_ms", "end_ms", "sort_order") else val
    if "start_ms" not in body: body["start_ms"] = 0
    if "end_ms" not in body: body["end_ms"] = 15000
    if "sort_order" not in body: body["sort_order"] = 1
    resp = api(c.host, c.auth, f"/api/v1/segments/{args.segment_id}/beats", "POST", body, c.timeout)
    data = out(resp, c.json)
    if data:
        print(f"节拍创建成功 beat_id={data.get('beat_id')}")
        return data.get("beat_id")


def cmd_edit_beat(args, c):
    fm = _field_map()["beat"]
    body = {}
    for flag, field in fm.items():
        val = getattr(args, flag, None)
        if val is not None:
            body[field] = int(val) if field in ("start_ms", "end_ms", "sort_order") else val
    if not body:
        print("未指定任何修改", file=sys.stderr); return
    resp = api(c.host, c.auth, f"/api/v1/beats/{args.beat_id}", "PATCH", body, c.timeout)
    data = out(resp, c.json)
    if data:
        print("节拍已更新")


def cmd_delete_beat(args, c):
    resp = api(c.host, c.auth, f"/api/v1/beats/{args.beat_id}", "DELETE", timeout=c.timeout)
    data = out(resp, c.json)
    if data:
        print("节拍已删除")


def cmd_list_assets(args, c):
    resp = api(c.host, c.auth, f"/api/v1/projects/{args.project_id}/assets", timeout=c.timeout)
    data = out(resp, c.json)
    if data:
        for a in data:
            print(f"{a['id'][:8]}  [{esc(a.get('asset_type'))}] {esc(a.get('name'))}  {esc(a.get('status'))}")


def cmd_create_asset(args, c):
    body = {"asset_type": args.type, "name": args.name}
    fm = _field_map()["asset"]
    for flag, field in fm.items():
        val = getattr(args, flag, None)
        if val is not None and field not in ("asset_type", "name"):
            body[field] = val
    resp = api(c.host, c.auth, f"/api/v1/projects/{args.project_id}/assets", "POST", body, c.timeout)
    data = out(resp, c.json)
    if data:
        print(f"资产创建成功 asset_id={data.get('asset_id')}")
        return data.get("asset_id")


def cmd_confirm_asset(args, c):
    resp = api(c.host, c.auth, f"/api/v1/assets/{args.asset_id}/confirm", "POST", timeout=c.timeout)
    data = out(resp, c.json)
    if data:
        print("资产已确认")


def cmd_build_prompt(args, c):
    resp = api(c.host, c.auth, f"/api/v1/segments/{args.segment_id}/keyframe-prompt/build", "POST", timeout=c.timeout)
    data = out(resp, c.json, quiet=True)
    if data:
        print("=== KEYFRAME PROMPT ===")
        print(data.get("keyframe_prompt"))
    resp2 = api(c.host, c.auth, f"/api/v1/segments/{args.segment_id}/h3-prompt/build", "POST", timeout=c.timeout)
    data2 = out(resp2, c.json, quiet=True)
    if data2:
        print("\n=== H3 PROMPT ===")
        print(data2.get("h3_prompt"))


def cmd_keyframe(args, c):
    if args.action == "view":
        resp = api(c.host, c.auth, f"/api/v1/segments/{args.segment_id}/keyframes", timeout=c.timeout)
        data = out(resp, c.json)
        if data:
            for k in data:
                print(f"{k['id'][:8]}  {k.get('status')}  {esc(k.get('image_path',''))}")
    elif args.action == "select":
        resp = api(c.host, c.auth, f"/api/v1/keyframes/{args.keyframe_id}/select", "POST", timeout=c.timeout)
        data = out(resp, c.json)
        if data:
            print("段首图已选定")
    elif args.action == "generate":
        resp = api(c.host, c.auth, f"/api/v1/segments/{args.segment_id}/keyframes/generate", "POST", timeout=c.timeout)
        data = out(resp, c.json)
        if data:
            print(f"段首图生成已排队 job={data.get('job_id')}")


def cmd_list_jobs(args, c):
    resp = api(c.host, c.auth, f"/api/v1/projects/{args.project_id}/jobs", timeout=c.timeout)
    data = out(resp, c.json)
    if data:
        for j in data:
            print(f"{j['id'][:8]}  {esc(j.get('job_type'))}  {esc(j.get('status'))}  target={esc(j.get('target_type'))}:{esc(j.get('target_id'))}  {esc(j.get('created_at',''))}")


def cmd_job_detail(args, c):
    resp = api(c.host, c.auth, f"/api/v1/jobs/{args.job_id}", timeout=c.timeout)
    data = out(resp, c.json)
    if data:
        print(json.dumps(data, ensure_ascii=False, indent=2))


def cmd_list_exports(args, c):
    resp = api(c.host, c.auth, f"/api/v1/projects/{args.project_id}/exports", timeout=c.timeout)
    data = out(resp, c.json)
    if data:
        for x in data:
            print(f"{x['id'][:8]}  {esc(x.get('title'))}  {esc(x.get('status'))}  {esc(x.get('created_at',''))}")


def cmd_context(args, c):
    """n2d context <project_id> — 聚合获取项目/分集/当前集/版本/段落/资产现状，供 agent 开场。"""
    resp = api(c.host, c.auth,
               f"/api/v1/projects/{args.project_id}/context?episode_id={args.episode or ''}&page={args.page or ''}",
               timeout=c.timeout)
    data = out(resp, c.json)   # json_mode 时已打印原始 JSON
    if data is None:
        return
    if c.json:
        return
    p = data.get("project", {})
    print(f"项目: {esc(p.get('name'))} [{esc(p.get('status'))}] 目标时长 {esc(p.get('target_duration_seconds'))}s")
    if p.get("description"):
        print(f"  描述: {esc(p['description'])[:120]}")
    if p.get("style_prompt"):
        print(f"  风格: {esc(p['style_prompt'])[:200]}")
    print("分集:")
    for e in data.get("episodes", []):
        mark = "*" if e.get("id") == data.get("current_episode") else " "
        print(f"  {mark} EP{e.get('episode_no')} {esc(e.get('title'))} ({e.get('id','')[:8]})")
    nv = data.get("novel_versions", {})
    print(f"小说版本: {nv.get('count')} 个，当前激活 '{esc(nv.get('active_title'))}' (文本 {nv.get('active_text_length')} 字)")
    seg = data.get("segments", {})
    print(f"段落: {seg.get('count')} 个")
    for s in seg.get("list", []):
        print(f"  [{s.get('sort_order')}] {esc(s.get('status'))} {esc(s.get('summary'))[:50]}")
    a = data.get("assets", {})
    print(f"资产: 角色 {a.get('characters')}，场景 {a.get('scenes')}")


def cmd_where(args, c):
    """n2d where [<session_key>] — 查看当前对话上下文（哪个用户 · 哪个项目 · 哪个页面）。"""
    if args.session_id:
        resp = api(c.host, c.auth, f"/api/v1/agent/sessions/{args.session_id}/context", timeout=c.timeout)
    else:
        resp = api(c.host, c.auth, "/api/v1/agent/sessions/latest", timeout=c.timeout)
    data = out(resp, c.json)   # json_mode 时已打印原始 JSON
    if data is None:
        return
    if c.json:
        return
    sess = data.get("session") or {}
    proj = data.get("project_name")
    print("当前对话上下文:")
    if proj:
        print(f"  项目: {esc(proj)}({esc(sess.get('project_id'))})")
    if sess.get("episode_id"):
        print(f"  当前分集: {esc(sess.get('episode_id'))}")
    if sess.get("page"):
        print(f"  页面: {esc(sess.get('page'))}")
    print(f"  用户: {esc(sess.get('operator') or '工作台用户')}")
    print(f"  会话: {esc(sess.get('id'))}")
    if data.get("last_user_message"):
        print(f"  最近指令: {esc(data['last_user_message'])[:120]}")


# ---------- argparse 构建 ----------
def build_parser():
    # 全局选项通过环境变量注入，不放在命令行, 保持简洁。这里加 --json
    p = argparse.ArgumentParser(prog="n2d", description="novel2drama 后端 CLI", add_help=True)
    p.add_argument("-j", "--json", action="store_true", help="输出原始 JSON")
    sub = p.add_subparsers(dest="cmd")

    sp = sub.add_parser("projects", help="列出项目")
    sp.set_defaults(func=cmd_projects)

    sp = sub.add_parser("project", help="项目操作")
    sp2 = sp.add_subparsers(dest="sub")
    sp_detail = sp2.add_parser("detail", help="项目详情")
    sp_detail.add_argument("project_id"); sp_detail.set_defaults(func=cmd_project_detail)
    sp_new = sp2.add_parser("new", help="创建项目")
    sp_new.add_argument("name")
    sp_new.add_argument("--desc"); sp_new.add_argument("--duration", type=int); sp_new.add_argument("--style")
    sp_new.set_defaults(func=cmd_create_project)
    sp_rm = sp2.add_parser("rm", help="删除项目")
    sp_rm.add_argument("project_id"); sp_rm.set_defaults(func=cmd_delete_project)

    sp = sub.add_parser("context", help="聚合获取项目现状(省 token，agent 开场)")
    sp.add_argument("project_id")
    sp.add_argument("--episode", help="指定当前集 id")
    sp.add_argument("--page", help="当前前端页面名")
    sp.set_defaults(func=cmd_context)

    sp = sub.add_parser("where", help="查看当前对话上下文(哪个用户·哪个项目·哪个页面)")
    sp.add_argument("session_id", nargs="?", help="会话 key（默认取最近活跃会话）")
    sp.set_defaults(func=cmd_where)

    sp = sub.add_parser("episodes", help="列出分集")
    sp.add_argument("project_id"); sp.set_defaults(func=cmd_list_episodes)

    sp = sub.add_parser("episode", help="分集操作")
    sp2 = sp.add_subparsers(dest="sub")
    sp_n = sp2.add_parser("new"); sp_n.add_argument("project_id"); sp_n.set_defaults(func=cmd_create_episode)

    sp = sub.add_parser("novels", help="小说版本列表")
    sp.add_argument("project_id"); sp.set_defaults(func=cmd_list_novels)

    sp = sub.add_parser("novel", help="小说版本操作")
    sp2 = sp.add_subparsers(dest="sub")
    sp_d = sp2.add_parser("detail"); sp_d.add_argument("version_id"); sp_d.set_defaults(func=cmd_novel_detail)
    sp_n = sp2.add_parser("new"); sp_n.add_argument("project_id"); sp_n.add_argument("title"); sp_n.add_argument("source")
    sp_n.set_defaults(func=cmd_create_novel)
    sp_a = sp2.add_parser("activate"); sp_a.add_argument("project_id"); sp_a.add_argument("version_id")
    sp_a.set_defaults(func=cmd_activate_novel)

    sp = sub.add_parser("chapters", help="章节列表")
    sp.add_argument("version_id"); sp.set_defaults(func=cmd_list_chapters)

    sp = sub.add_parser("chapter", help="章节操作")
    sp2 = sp.add_subparsers(dest="sub")
    sp_d = sp2.add_parser("detail"); sp_d.add_argument("chapter_id"); sp_d.set_defaults(func=cmd_chapter_detail)
    sp_p = sp2.add_parser("parse"); sp_p.add_argument("version_id"); sp_p.set_defaults(func=cmd_parse_chapters)
    sp_e = sp2.add_parser("edit"); sp_e.add_argument("chapter_id"); sp_e.add_argument("--title")
    sp_e.add_argument("--drop", action="store_true"); sp_e.add_argument("--include", action="store_true")
    sp_e.set_defaults(func=cmd_edit_chapter)
    sp_r = sp2.add_parser("rm"); sp_r.add_argument("chapter_id"); sp_r.set_defaults(func=cmd_delete_chapter)

    sp = sub.add_parser("segments", help="段落列表")
    sp.add_argument("project_id"); sp.set_defaults(func=cmd_list_segments)

    sp = sub.add_parser("seg", help="段操作")
    sp2 = sp.add_subparsers(dest="sub")
    sp_d = sp2.add_parser("detail"); sp_d.add_argument("project_id"); sp_d.add_argument("segment_id")
    sp_d.set_defaults(func=cmd_segment_detail)
    sp_n = sp2.add_parser("new"); sp_n.add_argument("project_id"); sp_n.add_argument("--no", type=int, required=True)
    sp_n.add_argument("--summary"); sp_n.add_argument("--start"); sp_n.add_argument("--end")
    sp_n.set_defaults(func=cmd_create_segment)
    sp_e = sp2.add_parser("edit"); sp_e.add_argument("project_id"); sp_e.add_argument("segment_id")
    sp_e.add_argument("--summary"); sp_e.add_argument("--start"); sp_e.add_argument("--end")
    sp_e.set_defaults(func=cmd_edit_segment)
    sp_r = sp2.add_parser("rm"); sp_r.add_argument("project_id"); sp_r.add_argument("segment_id")
    sp_r.set_defaults(func=cmd_delete_segment)

    sp = sub.add_parser("beats", help="节拍列表")
    sp.add_argument("segment_id"); sp.set_defaults(func=cmd_list_beats)

    sp = sub.add_parser("beat", help="节拍操作")
    sp2 = sp.add_subparsers(dest="sub")
    sp_n = sp2.add_parser("new"); sp_n.add_argument("segment_id")
    sp_n.add_argument("--start", type=int); sp_n.add_argument("--end", type=int); sp_n.add_argument("--no", type=int)
    sp_n.add_argument("--shot"); sp_n.add_argument("--camera"); sp_n.add_argument("--action")
    sp_n.add_argument("--scene"); sp_n.add_argument("--light"); sp_n.add_argument("--comp")
    sp_n.add_argument("--style"); sp_n.add_argument("--emotion"); sp_n.add_argument("--transition")
    sp_n.set_defaults(func=cmd_create_beat)
    sp_e = sp2.add_parser("edit"); sp_e.add_argument("beat_id")
    sp_e.add_argument("--start", type=int); sp_e.add_argument("--end", type=int); sp_e.add_argument("--no", type=int)
    sp_e.add_argument("--shot"); sp_e.add_argument("--camera"); sp_e.add_argument("--action")
    sp_e.add_argument("--scene"); sp_e.add_argument("--light"); sp_e.add_argument("--comp")
    sp_e.add_argument("--style"); sp_e.add_argument("--emotion"); sp_e.add_argument("--transition")
    sp_e.set_defaults(func=cmd_edit_beat)
    sp_r = sp2.add_parser("rm"); sp_r.add_argument("beat_id"); sp_r.set_defaults(func=cmd_delete_beat)

    sp = sub.add_parser("assets", help="资产列表")
    sp.add_argument("project_id"); sp.set_defaults(func=cmd_list_assets)

    sp = sub.add_parser("asset", help="资产操作")
    sp2 = sp.add_subparsers(dest="sub")
    sp_n = sp2.add_parser("new"); sp_n.add_argument("project_id"); sp_n.add_argument("--type", required=True)
    sp_n.add_argument("--name", required=True); sp_n.add_argument("--desc"); sp_n.add_argument("--appearance")
    sp_n.add_argument("--costume"); sp_n.add_argument("--temperament"); sp_n.add_argument("--time")
    sp_n.add_argument("--weather"); sp_n.add_argument("--lighting"); sp_n.add_argument("--color")
    sp_n.add_argument("--negative")
    sp_n.set_defaults(func=cmd_create_asset)
    sp_c = sp2.add_parser("confirm"); sp_c.add_argument("asset_id"); sp_c.set_defaults(func=cmd_confirm_asset)

    sp = sub.add_parser("builds", help="构建段首图/H3 prompt (写回后端)")
    sp.add_argument("segment_id"); sp.set_defaults(func=cmd_build_prompt)

    sp = sub.add_parser("kframe", help="段首图操作")
    sp2 = sp.add_subparsers(dest="sub")
    sp_v = sp2.add_parser("view"); sp_v.add_argument("segment_id")
    sp_v.set_defaults(func=cmd_keyframe, action="view")
    sp_s = sp2.add_parser("select"); sp_s.add_argument("keyframe_id")
    sp_s.set_defaults(func=cmd_keyframe, action="select")
    sp_g = sp2.add_parser("generate"); sp_g.add_argument("segment_id")
    sp_g.set_defaults(func=cmd_keyframe, action="generate")

    sp = sub.add_parser("jobs", help="任务列表")
    sp.add_argument("project_id"); sp.set_defaults(func=cmd_list_jobs)

    sp = sub.add_parser("job", help="任务详情")
    sp.add_argument("job_id"); sp.set_defaults(func=cmd_job_detail)

    sp = sub.add_parser("exports", help="导出列表")
    sp.add_argument("project_id"); sp.set_defaults(func=cmd_list_exports)

    return p


def main():
    parser = build_parser()
    args = parser.parse_args()
    if not getattr(args, "cmd", None):
        parser.print_help(); sys.exit(0)
    host = os.environ.get("N2D_HOST", DEFAULT_HOST)
    auth = os.environ.get("N2D_AUTH")
    # 局部的 c 容器
    c = argparse.Namespace(host=host, auth=auth, json=getattr(args, "json", False),
                           timeout=int(os.environ.get("N2D_TIMEOUT", "30")))
    try:
        args.func(args, c)
    except TypeError as e:
        # 某些命令的 func 可能缺参数, 兜底报错
        print(f"命令执行失败: {e}", file=sys.stderr)


if __name__ == "__main__":
    main()
