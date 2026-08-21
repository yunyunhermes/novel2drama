import sqlite3
import os

DB_PATH = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'data', 'novel2drama.db')
os.makedirs(os.path.dirname(DB_PATH), exist_ok=True)

def init():
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("""CREATE TABLE IF NOT EXISTS projects (
        id TEXT PRIMARY KEY, name TEXT NOT NULL, description TEXT,
        status TEXT NOT NULL DEFAULT 'draft', target_duration_seconds INTEGER,
        style_prompt TEXT, current_novel_version_id TEXT, data_dir TEXT NOT NULL,
        created_at TEXT NOT NULL, updated_at TEXT NOT NULL, deleted_at TEXT
    )""")
    c.execute("""CREATE TABLE IF NOT EXISTS novel_versions (
        id TEXT PRIMARY KEY, project_id TEXT NOT NULL, title TEXT NOT NULL,
        source_text TEXT NOT NULL, version_no INTEGER NOT NULL,
        is_active INTEGER NOT NULL DEFAULT 0, created_at TEXT NOT NULL
    )""")
    c.execute("""CREATE TABLE IF NOT EXISTS novel_chapters (
        id TEXT PRIMARY KEY, novel_version_id TEXT NOT NULL, title TEXT,
        content TEXT NOT NULL, sort_order INTEGER NOT NULL,
        included INTEGER NOT NULL DEFAULT 1, created_at TEXT NOT NULL, updated_at TEXT NOT NULL
    )""")
    c.execute("""CREATE TABLE IF NOT EXISTS segments (
        id TEXT PRIMARY KEY, project_id TEXT NOT NULL, novel_version_id TEXT,
        sort_order INTEGER NOT NULL, summary TEXT, start_transition TEXT,
        end_transition TEXT, keyframe_prompt TEXT, h3_prompt TEXT,
        negative_prompt TEXT, status TEXT NOT NULL DEFAULT 'draft',
        selected_keyframe_id TEXT, selected_h3_generation_id TEXT,
        created_at TEXT NOT NULL, updated_at TEXT NOT NULL
    )""")
    c.execute("""CREATE TABLE IF NOT EXISTS shot_beats (
        id TEXT PRIMARY KEY, segment_id TEXT NOT NULL, sort_order INTEGER NOT NULL,
        start_ms INTEGER NOT NULL, end_ms INTEGER NOT NULL, shot_size TEXT,
        camera_movement TEXT, character_action TEXT, scene_change TEXT,
        lighting TEXT, composition TEXT, style TEXT, emotion TEXT, transition TEXT,
        created_at TEXT NOT NULL, updated_at TEXT NOT NULL
    )""")
    c.execute("""CREATE TABLE IF NOT EXISTS assets (
        id TEXT PRIMARY KEY, project_id TEXT NOT NULL, asset_type TEXT NOT NULL,
        name TEXT NOT NULL, description TEXT, appearance_anchor TEXT,
        costume_anchor TEXT, temperament_anchor TEXT, time TEXT, weather TEXT,
        lighting TEXT, color_tendency TEXT, negative_prompt TEXT,
        status TEXT NOT NULL DEFAULT 'draft', selected_candidate_id TEXT,
        preview_candidate_id TEXT, created_at TEXT NOT NULL, updated_at TEXT NOT NULL
    )""")
    c.execute("""CREATE TABLE IF NOT EXISTS jobs (
        id TEXT PRIMARY KEY, project_id TEXT NOT NULL, job_type TEXT NOT NULL,
        target_type TEXT NOT NULL, target_id TEXT NOT NULL, payload_json TEXT NOT NULL,
        status TEXT NOT NULL DEFAULT 'queued', priority INTEGER NOT NULL DEFAULT 100,
        retry_count INTEGER NOT NULL DEFAULT 0, error_message TEXT,
        started_at TEXT, finished_at TEXT, created_at TEXT NOT NULL
    )""")
    c.execute("""CREATE TABLE IF NOT EXISTS reviews (
        id TEXT PRIMARY KEY, project_id TEXT NOT NULL, target_type TEXT NOT NULL,
        target_id TEXT NOT NULL, action TEXT NOT NULL, comment TEXT,
        reviewer TEXT, created_at TEXT NOT NULL
    )""")
    c.execute("""CREATE TABLE IF NOT EXISTS exports (
        id TEXT PRIMARY KEY, project_id TEXT NOT NULL, title TEXT NOT NULL,
        segment_ids_json TEXT NOT NULL, output_path TEXT, resolution TEXT,
        fps INTEGER, status TEXT NOT NULL DEFAULT 'draft', error_message TEXT,
        created_at TEXT NOT NULL, updated_at TEXT NOT NULL
    )""")
    conn.commit()
    conn.close()
    print('Database initialized at', DB_PATH)



def init_v2():
    """补齐第二版表 (asset_candidates/keyframes/h3_generations/agent_tasks/agent_patches)"""
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("""CREATE TABLE IF NOT EXISTS asset_candidates (
        id TEXT PRIMARY KEY, asset_id TEXT NOT NULL, generator TEXT NOT NULL,
        prompt TEXT NOT NULL, negative_prompt TEXT, image_path TEXT NOT NULL,
        seed TEXT, status TEXT NOT NULL, created_at TEXT NOT NULL
    )""")
    c.execute("""CREATE TABLE IF NOT EXISTS keyframes (
        id TEXT PRIMARY KEY, segment_id TEXT NOT NULL, generator TEXT NOT NULL,
        prompt TEXT NOT NULL, negative_prompt TEXT, image_path TEXT NOT NULL,
        seed TEXT, status TEXT NOT NULL, created_at TEXT NOT NULL
    )""")
    c.execute("""CREATE TABLE IF NOT EXISTS h3_generations (
        id TEXT PRIMARY KEY, segment_id TEXT NOT NULL, keyframe_id TEXT NOT NULL,
        prompt TEXT NOT NULL, negative_prompt TEXT, video_path TEXT,
        thumbnail_path TEXT, seed TEXT, workflow_name TEXT, params_json TEXT,
        status TEXT NOT NULL, error_message TEXT, created_at TEXT NOT NULL, updated_at TEXT NOT NULL
    )""")
    c.execute("""CREATE TABLE IF NOT EXISTS agent_tasks (
        id TEXT PRIMARY KEY, project_id TEXT NOT NULL, task_type TEXT NOT NULL,
        target_json TEXT NOT NULL, instruction TEXT, status TEXT NOT NULL,
        result_json TEXT, error_message TEXT, created_at TEXT NOT NULL, updated_at TEXT NOT NULL
    )""")
    c.execute("""CREATE TABLE IF NOT EXISTS agent_patches (
        id TEXT PRIMARY KEY, agent_task_id TEXT NOT NULL, project_id TEXT NOT NULL,
        patch_json TEXT NOT NULL, preview_json TEXT, status TEXT NOT NULL,
        applied_by TEXT, applied_at TEXT, created_at TEXT NOT NULL
    )""")
    c.execute("""CREATE TABLE IF NOT EXISTS segment_asset_refs (
        id TEXT PRIMARY KEY, segment_id TEXT NOT NULL, asset_type TEXT NOT NULL,
        asset_id TEXT NOT NULL, created_at TEXT NOT NULL
    )""")
    conn.commit()
    conn.close()
    print('Database v2 tables initialized')

if __name__ == '__main__':
    init()
    init_v2()
