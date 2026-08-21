from fastapi import APIRouter
from app.db import get_db
from app.models import ReviewCreate
import uuid
from datetime import datetime

router = APIRouter(tags=["review"])

def now():
    return datetime.utcnow().isoformat()

@router.get("/projects/{project_id}/reviews")
def list_reviews(project_id: str):
    db = get_db()
    rows = db.execute("SELECT * FROM reviews WHERE project_id=? ORDER BY created_at DESC", (project_id,)).fetchall()
    db.close()
    return {"success": True, "data": [dict(r) for r in rows]}

@router.post("/reviews")
def create_review(r: ReviewCreate):
    db = get_db()
    rid = str(uuid.uuid4())
    ts = now()
    db.execute("INSERT INTO reviews (id,project_id,target_type,target_id,action,comment,created_at) VALUES (?,?,?,?,?,?,?)",
               (rid, '', r.target_type, r.target_id, r.action, r.comment, ts))
    db.commit()
    db.close()
    return {"success": True, "data": {"review_id": rid}}
