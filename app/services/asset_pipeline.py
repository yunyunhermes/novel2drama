"""
资产生成流水线
Z-Image 抽卡 -> 人工选定 -> image2 预览 -> 确认入库
第一版只接 Z-Image 抽卡 + 选定 + 确认; image2 预览留接口.
"""
import uuid
from datetime import datetime
from typing import List, Dict, Any, Optional
from . import gateway_client, storage
from .prompt_builder import build_asset_anchor


def now():
    return datetime.utcnow().isoformat()


def generate_candidates(db, asset_id: str, count: int = 4,
                        prompt_override: Optional[str] = None,
                        size: str = "1024x1024") -> List[str]:
    """
    调用 Z-Image 为资产生成 count 张候选图
    返回 candidate_id 列表
    """
    asset = db.execute("SELECT * FROM assets WHERE id=?", (asset_id,)).fetchone()
    if not asset:
        raise ValueError("asset not found")
    asset = dict(asset)
    project_id = asset["project_id"]

    # 构建 prompt
    if prompt_override:
        prompt = prompt_override
    else:
        anchor = build_asset_anchor(asset)
        if asset["asset_type"] == "character":
            prompt = f"角色立绘, {asset['name']}, {asset.get('description','')}, {anchor}, 高质量, 细节丰富"
        else:
            prompt = f"场景概念图, {asset['name']}, {asset.get('description','')}, {anchor}, 高质量, 氛围感"
    negative = asset.get("negative_prompt") or "低质量, 模糊, 变形"

    candidate_ids = []
    for i in range(count):
        r = gateway_client.z_image_generate(prompt, negative_prompt=negative, size=size)
        img_bytes = gateway_client.z_image_download(r)
        fname = f"{uuid.uuid4().hex[:8]}_{i}.png"
        sub = f"assets/{'characters' if asset['asset_type']=='character' else 'scenes'}"
        abs_path = storage.save_bytes(project_id, sub, fname, img_bytes)
        rel_path = storage.get_rel_path(project_id, abs_path)

        cid = str(uuid.uuid4())
        db.execute(
            "INSERT INTO asset_candidates (id, asset_id, generator, prompt, negative_prompt, image_path, seed, status, created_at) "
            "VALUES (?,?,?,?,?,?,?,?,?)",
            (cid, asset_id, "z_image", prompt, negative, rel_path, None, "generated", now())
        )
        candidate_ids.append(cid)
    db.execute("UPDATE assets SET status='z_image_generated', updated_at=? WHERE id=?", (now(), asset_id))
    db.commit()
    return candidate_ids


def select_candidate(db, candidate_id: str) -> None:
    """选定某个候选 (不锁定, 可改选)"""
    row = db.execute("SELECT * FROM asset_candidates WHERE id=?", (candidate_id,)).fetchone()
    if not row:
        raise ValueError("candidate not found")
    row = dict(row)
    asset_id = row["asset_id"]
    # 重置同 asset 的其他候选状态
    db.execute("UPDATE asset_candidates SET status='generated' WHERE asset_id=?", (asset_id,))
    db.execute("UPDATE asset_candidates SET status='selected' WHERE id=?", (candidate_id,))
    db.execute("UPDATE assets SET selected_candidate_id=?, status='z_image_selected', updated_at=? WHERE id=?",
               (candidate_id, now(), asset_id))
    db.commit()


def confirm_asset(db, asset_id: str) -> None:
    """确认资产入库"""
    db.execute("UPDATE assets SET status='confirmed', updated_at=? WHERE id=?", (now(), asset_id))
    db.commit()
