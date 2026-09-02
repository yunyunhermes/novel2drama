"""
GPU Worker - 串行消费 jobs 表中的任务
支持任务类型:
- z_image_keyframe: Z-Image 段首图生成
- z_image_asset: Z-Image 资产候选图
- h3_segment: H3 15s 段生成
- ffmpeg_export: 视频拼接导出
- llm_storyboard: LLM 分镜生成 (可并行, 但也走队列统一管理)
"""
import json
import os
import sqlite3
import time
import uuid
from datetime import datetime
from typing import Dict, Any, Optional

from app.db import get_db
from app.services import gateway_client, storage, ffmpeg, asset_pipeline, storyboard_agent, xdit_client
from app.services.config import (
    WORKER_POLL_INTERVAL, PROJECTS_DATA_DIR, H3_QUALITY,
    H3_PREVIEW_SIZE, H3_HIGH_SIZE,
)


def now():
    return datetime.utcnow().isoformat()


def _update_job(db, job_id: str, status: str, error: Optional[str] = None):
    ts = now()
    if status == "running":
        db.execute("UPDATE jobs SET status=?, started_at=? WHERE id=?", (status, ts, job_id))
    elif status in ("succeeded", "failed", "canceled"):
        db.execute("UPDATE jobs SET status=?, finished_at=?, error_message=? WHERE id=?",
                   (status, ts, error, job_id))
    else:
        db.execute("UPDATE jobs SET status=?, error_message=? WHERE id=?", (status, error, job_id))
    db.commit()


def _get_payload(job: Dict[str, Any]) -> Dict[str, Any]:
    try:
        return json.loads(job.get("payload_json") or "{}")
    except Exception:
        return {}


# ============ 各类任务处理 ============
def handle_z_image_keyframe(db, job: Dict[str, Any]) -> None:
    """Z-Image 段首图生成"""
    p = _get_payload(job)
    segment_id = job["target_id"]
    count = p.get("count", 4)
    size = p.get("size", "1024x1024")

    seg = db.execute("SELECT * FROM segments WHERE id=?", (segment_id,)).fetchone()
    if not seg:
        raise ValueError("segment not found")
    seg = dict(seg)
    project_id = seg["project_id"]

    # 取段首节拍
    first_beat = db.execute(
        "SELECT * FROM shot_beats WHERE segment_id=? ORDER BY start_ms LIMIT 1",
        (segment_id,)).fetchone()
    first_beat = dict(first_beat) if first_beat else None

    # 取资产
    chars = [dict(r) for r in db.execute(
        "SELECT a.* FROM assets a JOIN segment_asset_refs r ON a.id=r.asset_id "
        "WHERE r.segment_id=? AND r.asset_type='character'", (segment_id,)).fetchall()]
    scenes = [dict(r) for r in db.execute(
        "SELECT a.* FROM assets a JOIN segment_asset_refs r ON a.id=r.asset_id "
        "WHERE r.segment_id=? AND r.asset_type='scene'", (segment_id,)).fetchall()]

    # 项目风格
    proj = db.execute("SELECT * FROM projects WHERE id=?", (project_id,)).fetchone()
    style_prompt = dict(proj).get("style_prompt") if proj else None

    from app.services.prompt_builder import build_keyframe_prompt, build_negative_prompt
    prompt = p.get("prompt_override") or seg.get("keyframe_prompt") or build_keyframe_prompt(
        seg, chars, scenes, style_prompt, first_beat)
    negative = build_negative_prompt(seg, chars, scenes)

    for i in range(count):
        r = gateway_client.z_image_generate(prompt, negative_prompt=negative, size=size)
        img_bytes = gateway_client.z_image_download(r)
        fname = f"{uuid.uuid4().hex[:8]}_{i}.png"
        abs_path = storage.save_bytes(project_id, "keyframes", fname, img_bytes)
        rel_path = storage.get_rel_path(project_id, abs_path)

        kid = str(uuid.uuid4())
        db.execute(
            "INSERT INTO keyframes (id, segment_id, generator, prompt, negative_prompt, image_path, seed, status, created_at) "
            "VALUES (?,?,?,?,?,?,?,?,?)",
            (kid, segment_id, "z_image", prompt, negative, rel_path, None, "generated", now()))
    db.execute("UPDATE segments SET status='keyframe_review', updated_at=? WHERE id=?", (now(), segment_id))
    db.commit()


def handle_z_image_asset(db, job: Dict[str, Any]) -> None:
    """Z-Image 资产候选图"""
    p = _get_payload(job)
    asset_id = job["target_id"]
    count = p.get("count", 4)
    prompt_override = p.get("prompt_override")
    asset_pipeline.generate_candidates(db, asset_id, count=count, prompt_override=prompt_override)


def handle_h3_segment(db, job: Dict[str, Any]) -> None:
    """H3 15s 段生成"""
    p = _get_payload(job)
    segment_id = job["target_id"]
    variant_count = p.get("variant_count", 1)

    seg = db.execute("SELECT * FROM segments WHERE id=?", (segment_id,)).fetchone()
    if not seg:
        raise ValueError("segment not found")
    seg = dict(seg)
    project_id = seg["project_id"]

    # 必须有选定的段首图
    if not seg.get("selected_keyframe_id"):
        raise ValueError("no selected keyframe")
    kf = db.execute("SELECT * FROM keyframes WHERE id=?", (seg["selected_keyframe_id"],)).fetchone()
    if not kf:
        raise ValueError("selected keyframe not found")
    kf = dict(kf)
    keyframe_abs = storage.get_abs_path(project_id, kf["image_path"])

    h3_prompt = p.get("prompt_override") or seg.get("h3_prompt")
    if not h3_prompt:
        raise ValueError("no h3_prompt")
    negative = seg.get("negative_prompt") or "低质量, 模糊, 变形"

    requested_quality = str(p.get("quality") or H3_QUALITY).lower()
    if requested_quality not in ("preview", "high"):
        raise ValueError("quality must be preview or high")
    quality = requested_quality
    client = gateway_client
    size = H3_PREVIEW_SIZE
    if requested_quality == "high":
        if xdit_client.is_available():
            client = xdit_client
            size = H3_HIGH_SIZE
        else:
            print("[gpu_worker] WARNING xDiT unavailable; falling back to preview")
            quality = "preview"

    for i in range(variant_count):
        task_id = client.h3_video_create(
            prompt=h3_prompt,
            first_frame_path=keyframe_abs,
            seconds=15,
            size=size,
            negative_prompt=negative,
        )
        status = client.h3_video_wait(task_id, timeout=1800, poll_interval=15)
        if client is xdit_client:
            video_bytes = client.h3_video_download(task_id, status=status)
        else:
            video_bytes = client.h3_video_download(task_id)
        fname = f"{uuid.uuid4().hex[:8]}_{i}.mp4"
        abs_path = storage.save_bytes(project_id, "h3_segments", fname, video_bytes)
        rel_path = storage.get_rel_path(project_id, abs_path)
        # 缩略图
        thumb_abs = abs_path.replace(".mp4", "_thumb.jpg")
        try:
            ffmpeg.extract_thumbnail(abs_path, thumb_abs, time_s=0.5)
            thumb_rel = storage.get_rel_path(project_id, thumb_abs)
        except Exception:
            thumb_rel = None

        gid = str(uuid.uuid4())
        db.execute(
            "INSERT INTO h3_generations (id, segment_id, keyframe_id, prompt, negative_prompt, "
            "video_path, thumbnail_path, seed, workflow_name, params_json, status, created_at, updated_at) "
            "VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)",
            (gid, segment_id, kf["id"], h3_prompt, negative, rel_path, thumb_rel,
             None, "h3_i2v", json.dumps({"task_id": task_id, "seconds": 15, "size": size, "quality": quality}),
             "generated", now(), now()))
    db.execute("UPDATE segments SET status='h3_review', updated_at=? WHERE id=?", (now(), segment_id))
    db.commit()


def handle_ffmpeg_export(db, job: Dict[str, Any]) -> None:
    """视频拼接导出"""
    p = _get_payload(job)
    export_id = job["target_id"]
    exp = db.execute("SELECT * FROM exports WHERE id=?", (export_id,)).fetchone()
    if not exp:
        raise ValueError("export not found")
    exp = dict(exp)
    project_id = exp["project_id"]

    segment_ids = json.loads(exp["segment_ids_json"])
    video_paths = []
    for sid in segment_ids:
        seg = db.execute("SELECT * FROM segments WHERE id=?", (sid,)).fetchone()
        if not seg or not dict(seg).get("selected_h3_generation_id"):
            raise ValueError(f"segment {sid} has no selected h3 generation")
        g = db.execute("SELECT * FROM h3_generations WHERE id=?",
                       (dict(seg)["selected_h3_generation_id"],)).fetchone()
        if not g:
            raise ValueError(f"h3 generation not found for segment {sid}")
        g = dict(g)
        video_paths.append(storage.get_abs_path(project_id, g["video_path"]))

    out_fname = f"export_{export_id[:8]}.mp4"
    out_abs = ffmpeg.concat_videos(
        project_id, video_paths, out_fname,
        resolution=exp.get("resolution"), fps=exp.get("fps"))
    out_rel = storage.get_rel_path(project_id, out_abs)

    db.execute("UPDATE exports SET output_path=?, status='succeeded', updated_at=? WHERE id=?",
               (out_rel, now(), export_id))
    db.commit()


def handle_llm_storyboard(db, job: Dict[str, Any]) -> None:
    """LLM 分镜生成"""
    p = _get_payload(job)
    project_id = job["project_id"]
    novel_version_id = p.get("novel_version_id")
    target_duration = p.get("target_duration_seconds", 180)
    episode_id = p.get("episode_id") or job.get("episode_id")

    nv = db.execute("SELECT * FROM novel_versions WHERE id=?", (novel_version_id,)).fetchone()
    if not nv:
        raise ValueError("novel version not found")
    nv = dict(nv)

    proj = db.execute("SELECT * FROM projects WHERE id=?", (project_id,)).fetchone()
    style_prompt = dict(proj).get("style_prompt") if proj else None

    result = storyboard_agent.generate_storyboard(
        nv["source_text"], target_duration, style_prompt)

    # 保存为 agent_task + patch
    task_id = str(uuid.uuid4())
    db.execute(
        "INSERT INTO agent_tasks (id, project_id, episode_id, task_type, target_json, instruction, status, result_json, created_at, updated_at) "
        "VALUES (?,?,?,?,?,?,?,?,?,?)",
        (task_id, project_id, episode_id, "generate_storyboard",
         json.dumps({"novel_version_id": novel_version_id}),
         f"生成 {target_duration}s 分镜", "succeeded",
         json.dumps(result), now(), now()))

    # 构造 patch (不直接应用, 等用户确认)
    # 先落资产 (create_asset), 再落分段 (create_segment)
    ops = []
    for ch in result.get("characters", []):
        ops.append({"type": "create_asset", "data": dict(ch, asset_type="character")})
    for sc in result.get("scenes", []):
        ops.append({"type": "create_asset", "data": dict(sc, asset_type="scene")})
    for seg in result.get("segments", []):
        ops.append({"type": "create_segment", "data": seg})
    patch_id = str(uuid.uuid4())
    db.execute(
        "INSERT INTO agent_patches (id, agent_task_id, project_id, episode_id, patch_json, status, created_at) "
        "VALUES (?,?,?,?,?,?,?)",
        (patch_id, task_id, project_id, episode_id, json.dumps({"ops": ops}), "pending", now()))
    db.commit()


# ============ 任务分发 ============
HANDLERS = {
    "z_image_keyframe": handle_z_image_keyframe,
    "z_image_asset": handle_z_image_asset,
    "h3_segment": handle_h3_segment,
    "ffmpeg_export": handle_ffmpeg_export,
    "llm_storyboard": handle_llm_storyboard,
}


def process_one_job() -> bool:
    """取一个 queued job 执行, 返回是否有任务被处理"""
    db = get_db()
    row = db.execute(
        "SELECT * FROM jobs WHERE status='queued' ORDER BY priority, created_at LIMIT 1"
    ).fetchone()
    if not row:
        db.close()
        return False
    job = dict(row)
    job_id = job["id"]
    _update_job(db, job_id, "running")
    try:
        handler = HANDLERS.get(job["job_type"])
        if not handler:
            raise ValueError(f"unknown job_type: {job['job_type']}")
        handler(db, job)
        _update_job(db, job_id, "succeeded")
    except Exception as e:
        _update_job(db, job_id, "failed", error=str(e)[:500])
    finally:
        db.close()
    return True


def run_forever():
    """主循环"""
    print(f"[gpu_worker] started, poll interval {WORKER_POLL_INTERVAL}s")
    while True:
        try:
            if not process_one_job():
                time.sleep(WORKER_POLL_INTERVAL)
        except Exception as e:
            print(f"[gpu_worker] loop error: {e}")
            time.sleep(WORKER_POLL_INTERVAL)


if __name__ == "__main__":
    run_forever()
