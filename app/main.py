import json
import uuid
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, File, Form, HTTPException, UploadFile
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from . import db
from .analyzers import analyze, score, sha256_file, text_fingerprint
from .analyzers.ocr import ocr_available

ROOT = Path(__file__).resolve().parent.parent
UPLOADS = ROOT / "data" / "uploads"
STATIC = ROOT / "static"
MAX_BYTES = 25 * 1024 * 1024
EXTENSIONS = {".pdf": "pdf", ".jpg": "image", ".jpeg": "image", ".png": "image",
              ".tif": "image", ".tiff": "image", ".webp": "image", ".bmp": "image"}
DOC_TYPES = ["Invoice", "GST certificate", "PAN card", "Aadhaar", "Bank statement",
             "Cancelled cheque", "Experience letter", "Degree certificate", "Other"]

@asynccontextmanager
async def lifespan(_app):
    UPLOADS.mkdir(parents=True, exist_ok=True)
    db.init()
    yield


app = FastAPI(title="Document Verification", lifespan=lifespan)


@app.get("/api/config")
def config():
    return {"ocr": ocr_available(), "doc_types": DOC_TYPES, "max_mb": MAX_BYTES // (1024 * 1024)}


@app.post("/api/documents")
async def upload(file: UploadFile = File(...), doc_type: str = Form("Other")):
    ext = Path(file.filename or "").suffix.lower()
    kind = EXTENSIONS.get(ext)
    if not kind:
        raise HTTPException(400, f"Unsupported file type '{ext}'. Allowed: {', '.join(EXTENSIONS)}")

    data = await file.read()
    if len(data) > MAX_BYTES:
        raise HTTPException(413, "File too large")
    if kind == "pdf" and not data.startswith(b"%PDF"):
        raise HTTPException(400, "File has a .pdf extension but is not a PDF")

    stored = f"{uuid.uuid4().hex}{ext}"
    path = UPLOADS / stored
    path.write_bytes(data)
    ela_path = UPLOADS / f"{path.stem}_ela.png"

    try:
        result = analyze(str(path), kind, str(ela_path))
    except Exception as exc:
        path.unlink(missing_ok=True)
        raise HTTPException(422, f"Could not analyze file: {exc}")

    findings = result["findings"]
    sha = sha256_file(path)
    text_hash = text_fingerprint(result["text"])

    with db.connect() as c:
        dup = c.execute("SELECT id, filename FROM documents WHERE sha256 = ? ORDER BY id LIMIT 1",
                        (sha,)).fetchone()
        if dup:
            findings.append({"severity": "medium", "category": "duplicate",
                             "title": f"Exact duplicate of document #{dup['id']}",
                             "detail": f"Same file was already submitted as '{dup['filename']}'."})
        elif text_hash:
            near = c.execute("SELECT id, filename FROM documents WHERE text_hash = ? ORDER BY id LIMIT 1",
                             (text_hash,)).fetchone()
            if near:
                findings.append({"severity": "medium", "category": "duplicate",
                                 "title": f"Same text content as document #{near['id']}",
                                 "detail": f"Different file, identical text to '{near['filename']}'. "
                                           "Possible re-submission or template reuse."})

        risk, status = score(findings)
        cur = c.execute(
            """INSERT INTO documents (filename, stored_name, kind, size, sha256, text_hash, doc_type,
                   risk_score, auto_status, has_ela, findings, fields, meta, text_excerpt)
               VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
            (file.filename, stored, kind, len(data), sha, text_hash, doc_type, risk, status,
             int(ela_path.exists()), json.dumps(findings), json.dumps(result["fields"]),
             json.dumps(result["meta"], default=str), result["text"][:5000]),
        )
        row = c.execute("SELECT * FROM documents WHERE id = ?", (cur.lastrowid,)).fetchone()
    return db.row_to_dict(row)


@app.get("/api/documents")
def list_documents(status: str | None = None, q: str | None = None):
    sql, args = "SELECT * FROM documents WHERE 1=1", []
    if status in ("passed", "review", "flagged"):
        sql += " AND auto_status = ?"
        args.append(status)
    elif status in ("pending", "approved", "rejected"):
        sql += " AND review_status = ?"
        args.append(status)
    if q:
        sql += " AND (filename LIKE ? OR doc_type LIKE ? OR text_excerpt LIKE ?)"
        args += [f"%{q}%"] * 3
    sql += " ORDER BY id DESC LIMIT 500"
    with db.connect() as c:
        return [db.row_to_dict(r, full=False) for r in c.execute(sql, args)]


@app.get("/api/stats")
def stats():
    with db.connect() as c:
        r = c.execute("""SELECT COUNT(*) total,
                SUM(auto_status='passed') passed, SUM(auto_status='review') review,
                SUM(auto_status='flagged') flagged, SUM(review_status='pending') pending
            FROM documents""").fetchone()
    return {k: (r[k] or 0) for k in r.keys()}


def _get(doc_id):
    with db.connect() as c:
        row = c.execute("SELECT * FROM documents WHERE id = ?", (doc_id,)).fetchone()
    if not row:
        raise HTTPException(404, "Document not found")
    return row


@app.get("/api/documents/{doc_id}")
def get_document(doc_id: int):
    return db.row_to_dict(_get(doc_id))


class Review(BaseModel):
    decision: str
    note: str = ""


@app.post("/api/documents/{doc_id}/review")
def review(doc_id: int, body: Review):
    if body.decision not in ("approved", "rejected", "pending"):
        raise HTTPException(400, "decision must be approved, rejected or pending")
    _get(doc_id)
    with db.connect() as c:
        c.execute("""UPDATE documents SET review_status = ?, reviewer_note = ?,
                     reviewed_at = datetime('now', 'localtime') WHERE id = ?""",
                  (body.decision, body.note.strip(), doc_id))
    return get_document(doc_id)


@app.get("/api/documents/{doc_id}/file")
def get_file(doc_id: int):
    row = _get(doc_id)
    return FileResponse(UPLOADS / row["stored_name"], filename=row["filename"],
                        content_disposition_type="inline")


@app.get("/api/documents/{doc_id}/ela")
def get_ela(doc_id: int):
    row = _get(doc_id)
    path = UPLOADS / f"{Path(row['stored_name']).stem}_ela.png"
    if not path.exists():
        raise HTTPException(404, "No ELA image for this document")
    return FileResponse(path, media_type="image/png")


@app.delete("/api/documents/{doc_id}")
def delete_document(doc_id: int):
    row = _get(doc_id)
    stem = Path(row["stored_name"]).stem
    (UPLOADS / row["stored_name"]).unlink(missing_ok=True)
    (UPLOADS / f"{stem}_ela.png").unlink(missing_ok=True)
    with db.connect() as c:
        c.execute("DELETE FROM documents WHERE id = ?", (doc_id,))
    return {"deleted": doc_id}


app.mount("/", StaticFiles(directory=STATIC, html=True), name="static")
