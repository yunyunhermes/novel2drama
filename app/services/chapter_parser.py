"""章节解析器：把小说原文切分成章节。

支持的章节标记（按优先级）：
1. 第X章 / 第X回 / 第X卷 / 第X节 （X 为中文数字或阿拉伯数字）
2. Chapter N / CHAPTER N / Chap. N
3. 序章 / 楔子 / 尾声 / 番外
4. 数字开头：1. / 1、/ 1 标题
5. fallback：找不到标记时按空行+长度切分（每块 >= min_chars 视为一章）

不做超长文本深度解析（用户 2026-08-22 明确暂不做），仅做基于行首标记的浅切分。
"""
from __future__ import annotations
import re
from dataclasses import dataclass
from typing import List

# 章节标题正则（行首匹配，整行视为标题）
CHAPTER_PATTERNS = [
    # 第X章/回/卷/节/部/篇，X 为中文数字或阿拉伯数字，可带冒号或空格后跟标题
    re.compile(r"^\s*第[0-9零一二三四五六七八九十百千万两]+[章回卷节部篇][：:\s]?.*$"),
    # Chapter N / CHAPTER N
    re.compile(r"^\s*[Cc][Hh][Aa][Pp][Tt][Ee][Rr]\s+\d+.*$"),
    # 序章/楔子/尾声/番外/前言/后记
    re.compile(r"^\s*(序章|楔子|尾声|番外|前言|后记|序|引子)\b.*$"),
    # 数字开头：1. 标题 / 1、标题 / 1 标题（行首+最多 50 字符）
    re.compile(r"^\s*\d{1,4}[\.、\s]\s*\S.{0,50}$"),
]

# 标题行最大长度（超过视为正文）
MAX_TITLE_LEN = 60


@dataclass
class Chapter:
    title: str
    content: str
    sort_order: int


def _is_chapter_heading(line: str) -> bool:
    line = line.strip()
    if not line or len(line) > MAX_TITLE_LEN:
        return False
    return any(p.match(line) for p in CHAPTER_PATTERNS)


def parse_chapters(source_text: str, min_chars_fallback: int = 2000) -> List[Chapter]:
    """把原文切成章节列表。"""
    if not source_text or not source_text.strip():
        return []

    lines = source_text.splitlines()
    chapters: List[Chapter] = []
    current_title = ""
    current_buf: List[str] = []
    order = 1

    def flush():
        nonlocal current_title, current_buf, order
        content = "\n".join(current_buf).strip()
        if not content and not current_title:
            return
        title = current_title or f"第 {order} 节"
        chapters.append(Chapter(title=title, content=content, sort_order=order))
        order += 1
        current_title = ""
        current_buf = []

    for line in lines:
        if _is_chapter_heading(line):
            flush()
            current_title = line.strip()
        else:
            current_buf.append(line)
    flush()

    # fallback：全文没有任何章节标记 → 按空行+长度切
    if len(chapters) <= 1:
        chapters = _fallback_split(source_text, min_chars_fallback)

    return chapters


def _fallback_split(text: str, min_chars: int) -> List[Chapter]:
    """没有章节标记时，按空行段落聚合到 min_chars 切一刀。"""
    paras = [p.strip() for p in re.split(r"\n\s*\n", text) if p.strip()]
    chapters: List[Chapter] = []
    buf: List[str] = []
    buf_len = 0
    order = 1
    for p in paras:
        buf.append(p)
        buf_len += len(p)
        if buf_len >= min_chars:
            chapters.append(Chapter(
                title=f"第 {order} 节",
                content="\n\n".join(buf),
                sort_order=order,
            ))
            order += 1
            buf = []
            buf_len = 0
    if buf:
        chapters.append(Chapter(
            title=f"第 {order} 节",
            content="\n\n".join(buf),
            sort_order=order,
        ))
    return chapters
