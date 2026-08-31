from pydantic import BaseModel
from typing import Optional, List
from datetime import datetime

class ProjectCreate(BaseModel):
    name: str
    description: Optional[str] = None
    target_duration_seconds: Optional[int] = None
    style_prompt: Optional[str] = None

class NovelVersionCreate(BaseModel):
    title: str
    source_text: str
    episode_id: Optional[str] = None

class SegmentCreate(BaseModel):
    sort_order: int
    summary: Optional[str] = None
    start_transition: Optional[str] = None
    end_transition: Optional[str] = None
    episode_id: Optional[str] = None

class ShotBeatCreate(BaseModel):
    sort_order: int
    start_ms: int
    end_ms: int
    shot_size: Optional[str] = None
    camera_movement: Optional[str] = None
    character_action: Optional[str] = None
    scene_change: Optional[str] = None
    lighting: Optional[str] = None
    composition: Optional[str] = None
    style: Optional[str] = None
    emotion: Optional[str] = None
    transition: Optional[str] = None

class AssetCreate(BaseModel):
    asset_type: str
    name: str
    description: Optional[str] = None
    appearance_anchor: Optional[str] = None
    costume_anchor: Optional[str] = None
    temperament_anchor: Optional[str] = None
    time: Optional[str] = None
    weather: Optional[str] = None
    lighting: Optional[str] = None
    color_tendency: Optional[str] = None
    negative_prompt: Optional[str] = None

class JobCreate(BaseModel):
    job_type: str
    target_type: str
    target_id: str
    payload_json: str
    episode_id: Optional[str] = None

class ReviewCreate(BaseModel):
    target_type: str
    target_id: str
    action: str
    comment: Optional[str] = None
    project_id: Optional[str] = None
    episode_id: Optional[str] = None

class ExportCreate(BaseModel):
    title: str
    segment_ids: List[str]
    resolution: Optional[str] = "1080p"
    fps: Optional[int] = 24
