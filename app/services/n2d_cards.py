"""把 n2d 命令翻译成高可读的中文行为卡片（不向前端透出原始命令）。

supply: is_write_cmd(command) -> bool ; render_action(command) -> str
"""
import shlex
import re

# 变体动词 → 视为写操作（n2d 里会改库的操作）
WRITE_SUBVERBS = {
    "new", "edit", "rm", "delete", "create", "activate", "confirm",
    "parse", "generate", "select", "apply", "reject", "include", "drop",
}

# (verb, subverb) -> 中文动作标签
VERB_ACTION = {
    ("seg", "new"): "新建段落",
    ("seg", "edit"): "修改段落",
    ("seg", "rm"): "删除段落",
    ("chapter", "parse"): "重排章节",
    ("chapter", "edit"): "修改章节",
    ("chapter", "rm"): "删除章节",
    ("novel", "new"): "新建小说版本",
    ("novel", "activate"): "切换当前小说版本",
    ("beat", "new"): "新增节拍",
    ("beat", "edit"): "修改节拍",
    ("beat", "rm"): "删除节拍",
    ("asset", "new"): "创建资产",
    ("asset", "confirm"): "确认资产",
    ("project", "new"): "创建项目",
    ("project", "rm"): "删除项目",
    ("episode", "new"): "新建分集",
    ("keyframe", "generate"): "生成段首图",
    ("keyframe", "select"): "选定段首图",
    ("kframe", "generate"): "生成段首图",
    ("kframe", "select"): "选定段首图",
}

# 面向展示的字段抓取（--flag value），用于在卡里附一句关键内容（不含命令）
FIELD_LABEL = {
    "summary": "剧情摘要",
    "title": "标题",
    "name": "名称",
    "description": "描述",
    "start_transition": "段首衔接",
    "end_transition": "段尾衔接",
    "source_text": "正文",
}


def _tokens(cmd):
    try:
        return shlex.split(cmd)
    except Exception:
        return cmd.split()


def is_write_cmd(command):
    """判断 n2d 命令是否为写操作（改库），是 -> 需前端确认。"""
    tokens = _tokens(command or "")
    if not tokens or tokens[0] != "n2d":
        # 非 n2d 命令（其他 shell）视为写操作以外的普通工具，默认放行
        return False
    verb = tokens[1] if len(tokens) > 1 else ""
    sub = tokens[2] if len(tokens) > 2 and not tokens[2].startswith("-") else ""
    # 读命令（含 context 聚合现状 / where 对话上下文）一律放行，不弹行为卡片
    if verb in ("context", "where"):
        return False
    if verb in WRITE_SUBVERBS or sub in WRITE_SUBVERBS:
        return True
    # chapter edit/include 等带 -- 的（verb=chapter, sub 可能带 flag 前）细判
    return False


def render_action(command):
    """把 n2d 命令渲染成可读中文描述（不含原始命令）。"""
    tokens = _tokens(command or "")
    if not tokens:
        return "执行操作"
    if tokens[0] != "n2d":
        # 非 n2d 工具：给一个中性标签，不暴露命令串
        tool = tokens[0].split("/")[-1] if tokens[0] else "命令"
        return f"调用工具：{tool}"
    verb = tokens[1] if len(tokens) > 1 else ""
    sub = tokens[2] if len(tokens) > 2 and not tokens[2].startswith("-") else ""
    label = VERB_ACTION.get((verb, sub))
    if not label:
        # 兜底：拆动词字面
        if verb in WRITE_SUBVERBS:
            label = {"new": "新建", "edit": "修改", "rm": "删除", "delete": "删除",
                     "create": "创建", "activate": "激活", "confirm": "确认",
                     "parse": "解析", "generate": "生成", "select": "选定",
                     "apply": "应用", "reject": "拒绝", "include": "纳入", "drop": "排除"}.get(verb, verb)
        elif sub in WRITE_SUBVERBS:
            label = {"new": "新建", "edit": "修改", "rm": "删除", "delete": "删除",
                     "create": "创建", "activate": "激活", "confirm": "确认",
                     "parse": "解析", "generate": "生成", "select": "选定",
                     "apply": "应用", "reject": "拒绝", "include": "纳入", "drop": "排除"}.get(sub, sub) + f"{verb}"
        else:
            label = f"操作 {verb}"
    # 附加一句用户可读的关键内容（--summary / --title / --name 等）
    detail = _detail_from_tokens(tokens)
    if detail:
        return f"{label}（{detail}）"
    return label


def _detail_from_tokens(tokens):
    parts = []
    i = 0
    while i < len(tokens):
        t = tokens[i]
        if t.startswith("--") and i + 1 < len(tokens):
            key = t[2:]
            val = tokens[i + 1]
            lab = FIELD_LABEL.get(key, key)
            val = _clean(val)
            if val and key in FIELD_LABEL and len(val) > 2:
                parts.append(f"{lab}：{val[:18]}{'…' if len(val) > 18 else ''}")
            i += 2
        else:
            i += 1
    return "；".join(parts[:3])


def _clean(v):
    v = (v or "").strip().strip('"').strip("'")
    return v
