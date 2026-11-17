
import shutil
import uuid
from pathlib import Path

from fastapi import (
    FastAPI,
    UploadFile,
    WebSocket,
    WebSocketDisconnect,
    HTTPException,
    Depends
)
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from database import client, init_db
from auth import (
    router as auth_router,
    get_current_user,
    require_admin
)
from yolo import detect
from ws_manager import manager
from risk import predict_risk


# --------------------------------------------------
# DATABASE INITIALIZATION AND SAFE MIGRATIONS
# --------------------------------------------------

init_db()

report_columns = client.execute(
    "PRAGMA table_info(reports)"
).rows

existing_report_columns = [column[1] for column in report_columns]

report_migrations = [
    ("lat", "REAL"),
    ("lon", "REAL"),
    ("risk_level", "TEXT"),
    ("location_source", "TEXT"),
    ("region", "TEXT"),
    ("risk_probability", "REAL"),
    ("nearest_hotspot", "TEXT"),
    ("user_id", "INTEGER"),
    ("status", "TEXT NOT NULL DEFAULT 'approved'")
]

for column_name, column_type in report_migrations:
    if column_name not in existing_report_columns:
        client.execute(
            f"ALTER TABLE reports ADD COLUMN {column_name} {column_type}"
        )


# Shared notifications; read status is maintained per account.
client.execute("""
CREATE TABLE IF NOT EXISTS notifications (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    title TEXT NOT NULL,
    body TEXT,
    created_at TEXT DEFAULT CURRENT_TIMESTAMP
)
""")

client.execute("""
CREATE TABLE IF NOT EXISTS notification_reads (
    notification_id INTEGER NOT NULL,
    user_email TEXT NOT NULL,
    PRIMARY KEY (notification_id, user_email)
)
""")


def add_notification(title: str, body: str):
    client.execute(
        "INSERT INTO notifications (title, body) VALUES (?, ?)",
        [title, body]
    )


# --------------------------------------------------
# REQUEST MODELS
# --------------------------------------------------

class ReportSubmission(BaseModel):
    image_path: str
    species: str
    confidence: float
    lat: float | None = None
    lon: float | None = None
    location_source: str = "GPS"


# --------------------------------------------------
# FASTAPI APPLICATION
# --------------------------------------------------

app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"]
)

app.include_router(auth_router)

Path("uploads").mkdir(exist_ok=True)

app.mount(
    "/uploads",
    StaticFiles(directory="uploads"),
    name="uploads"
)


# --------------------------------------------------
# PUBLIC ANIMAL DETECTION PREVIEW
# Does NOT create a report or notification.
# --------------------------------------------------

@app.post("/api/detect-animal")
async def detect_animal(
    file: UploadFile,
    reported_by: str = "anonymous",
    lat: float = None,
    lon: float = None,
    location_source: str = "GPS"
):
    uploads_dir = Path("uploads")
    uploads_dir.mkdir(exist_ok=True)

    extension = Path(file.filename or "").suffix.lower()

    if extension not in [".jpg", ".jpeg", ".png", ".webp"]:
        extension = ".jpg"

    path = str(
        uploads_dir / f"{uuid.uuid4().hex}{extension}"
    )

    try:
        with open(path, "wb") as output_file:
            shutil.copyfileobj(file.file, output_file)
    finally:
        await file.close()

    result = detect(path)
    species, confidence = result if result else ("Unknown", 0.0)

    risk_data = None

    if lat is not None and lon is not None:
        try:
            risk_data = predict_risk(lat, lon, species)
        except Exception as error:
            print(f"Risk prediction failed: {error}")

    return {
        "species": species,
        "confidence": confidence,
        "lat": lat,
        "lon": lon,
        "location_source": location_source,
        "image_path": path,
        "risk": risk_data
    }


# --------------------------------------------------
# AUTHENTICATED REPORT SUBMISSION
# New reports are PENDING until administrator approval.
# --------------------------------------------------

@app.post("/api/reports")
def submit_report(
    submission: ReportSubmission,
    current_user: dict = Depends(get_current_user)
):
    if submission.confidence < 0 or submission.confidence > 1:
        raise HTTPException(400, "Invalid detection confidence")

    if not submission.species.strip():
        raise HTTPException(400, "Species is required")

    uploads_dir = Path("uploads").resolve()
    image_path = Path(submission.image_path)

    if image_path.is_absolute():
        resolved_image = image_path.resolve()
    else:
        resolved_image = (Path.cwd() / image_path).resolve()

    if resolved_image.parent != uploads_dir:
        raise HTTPException(400, "Invalid image path")

    if not resolved_image.is_file():
        raise HTTPException(400, "Detection image not found")

    # Recalculate risk on the server rather than trusting
    # risk values supplied by the browser.
    risk_data = None

    if submission.lat is not None and submission.lon is not None:
        try:
            risk_data = predict_risk(
                submission.lat,
                submission.lon,
                submission.species
            )
        except Exception as error:
            print(f"Risk prediction failed: {error}")

    risk_level = risk_data.get("risk_level") if risk_data else None
    region = risk_data.get("region") if risk_data else None
    risk_probability = (
        risk_data.get("high_risk_prob") if risk_data else None
    )
    nearest_hotspot = (
        risk_data.get("nearest_hotspot") if risk_data else None
    )

    result = client.execute(
        """
        INSERT INTO reports (
            species, confidence, image_path, reported_by,
            lat, lon, risk_level, location_source,
            region, risk_probability, nearest_hotspot,
            user_id, status
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'pending')
        """,
        [
            submission.species,
            submission.confidence,
            str(resolved_image.relative_to(Path.cwd())),
            current_user["name"],
            submission.lat,
            submission.lon,
            risk_level,
            submission.location_source,
            region,
            risk_probability,
            nearest_hotspot,
            current_user["id"]
        ]
    )

    return {
        "ok": True,
        "status": "pending",
        "message": "Your report was submitted for administrator review.",
        "risk": risk_data
    }


# --------------------------------------------------
# PUBLIC APPROVED REPORTS
# --------------------------------------------------

def format_report(row):
    return {
        "id": row[0],
        "species": row[1],
        "confidence": row[2],
        "reported_by": row[3],
        "created_at": row[4],
        "lat": row[5],
        "lon": row[6],
        "risk_level": row[7],
        "image_path": row[8],
        "location_source": row[9],
        "region": row[10],
        "risk_probability": row[11],
        "nearest_hotspot": row[12],
        "status": row[13]
    }


REPORT_SELECT = """
    SELECT
        rowid, species, confidence, reported_by, created_at,
        lat, lon, risk_level, image_path,
        location_source, region, risk_probability,
        nearest_hotspot, status
    FROM reports
"""


@app.get("/api/reports")
def get_reports():
    result = client.execute(
        REPORT_SELECT + """
        WHERE status = 'approved'
        ORDER BY created_at DESC
        """
    )

    return [format_report(row) for row in result.rows]


# --------------------------------------------------
# USER'S OWN REPORTS
# --------------------------------------------------

@app.get("/api/my-reports")
def get_my_reports(
    current_user: dict = Depends(get_current_user)
):
    result = client.execute(
        REPORT_SELECT + """
        WHERE user_id = ?
        ORDER BY created_at DESC
        """,
        [current_user["id"]]
    )

    return [format_report(row) for row in result.rows]


# --------------------------------------------------
# ADMIN: VIEW PENDING REPORTS
# --------------------------------------------------

@app.get("/api/admin/reports")
def get_pending_reports(
    admin: dict = Depends(require_admin)
):
    result = client.execute(
        REPORT_SELECT + """
        WHERE status = 'pending'
        ORDER BY created_at DESC
        """
    )

    return [format_report(row) for row in result.rows]


# --------------------------------------------------
# ADMIN: APPROVE OR REJECT REPORTS
# --------------------------------------------------

@app.post("/api/admin/reports/{report_id}/review")
async def review_report(
    report_id: int,
    status: str,
    admin: dict = Depends(require_admin)
):
    status = status.strip().lower()

    if status not in ["approved", "rejected"]:
        raise HTTPException(
            400,
            "Status must be approved or rejected"
        )

    result = client.execute(
        """
        SELECT species, confidence, reported_by, lat, lon,
               risk_level, location_source, region,
               risk_probability, nearest_hotspot, image_path
        FROM reports
        WHERE rowid = ? AND status = 'pending'
        """,
        [report_id]
    )

    if not result.rows:
        raise HTTPException(
            404,
            "Pending report not found"
        )

    client.execute(
        "UPDATE reports SET status = ? WHERE rowid = ?",
        [status, report_id]
    )

    row = result.rows[0]

    if status == "approved":
        await manager.broadcast({
            "type": "detection",
            "id": report_id,
            "species": row[0],
            "confidence": row[1],
            "reported_by": row[2],
            "lat": row[3],
            "lon": row[4],
            "risk_level": row[5],
            "location_source": row[6],
            "region": row[7],
            "risk_probability": row[8],
            "nearest_hotspot": row[9],
            "image_path": row[10]
        })

        add_notification(
            f"New approved report: {row[0]}",
            f"An incident report submitted by {row[2]} "
            "has been verified and published."
        )

    return {
        "ok": True,
        "id": report_id,
        "status": status
    }


# --------------------------------------------------
# ADMIN: ESCALATE REPORT RISK
# --------------------------------------------------

_RISK_ESCALATION = {
    "LOW": "MEDIUM",
    "MEDIUM": "HIGH",
    "HIGH": "HIGH"
}


@app.post("/api/reports/{report_id}/escalate")
async def escalate_report(
    report_id: int,
    admin: dict = Depends(require_admin)
):
    result = client.execute(
        """
        SELECT species, risk_level
        FROM reports
        WHERE rowid = ? AND status = 'approved'
        """,
        [report_id]
    )

    if not result.rows:
        raise HTTPException(
            404,
            "Approved report not found"
        )

    species, current_risk = result.rows[0]

    current_risk = (current_risk or "LOW").upper()
    new_risk = _RISK_ESCALATION.get(current_risk, "HIGH")

    client.execute(
        "UPDATE reports SET risk_level = ? WHERE rowid = ?",
        [new_risk, report_id]
    )

    await manager.broadcast({
        "type": "escalation",
        "id": report_id,
        "species": species,
        "risk_level": new_risk,
        "escalated_by": admin["name"]
    })

    add_notification(
        f"Risk escalated: {species}",
        f"Escalated from {current_risk} to {new_risk} "
        f"by {admin['name']}."
    )

    return {
        "id": report_id,
        "risk_level": new_risk
    }


# --------------------------------------------------
# PUBLIC WEBSOCKET ALERTS
# --------------------------------------------------

@app.websocket("/ws/alerts")
async def ws_alerts(ws: WebSocket):
    await manager.connect(ws)

    try:
        while True:
            await ws.receive_text()
    except WebSocketDisconnect:
        manager.disconnect(ws)


# --------------------------------------------------
# PUBLIC RISK PREDICTION
# --------------------------------------------------

@app.get("/api/predict-risk")
def risk(
    lat: float,
    lon: float,
    species: str = None,
    month: int = None
):
    return predict_risk(lat, lon, species, month)


# --------------------------------------------------
# ADMIN: CREATE OFFICIAL NOTIFICATION
# --------------------------------------------------

@app.post("/api/notifications")
def create_notification(
    title: str,
    body: str = "",
    admin: dict = Depends(require_admin)
):
    if not title.strip():
        raise HTTPException(400, "Notification title is required")

    add_notification(title, body)

    return {"ok": True}


# --------------------------------------------------
# AUTHENTICATED NOTIFICATION LIST
# Read status is derived from the verified JWT identity.
# --------------------------------------------------


@app.get("/api/notifications")
def list_notifications(
    limit: int = 10,
    offset: int = 0,
    current_user: dict = Depends(get_current_user)
):
    limit = max(1, min(limit, 100))
    offset = max(0, offset)

    result = client.execute(
        """
        SELECT n.id, n.title, n.body, n.created_at,
               CASE WHEN r.user_email IS NULL THEN 0 ELSE 1 END
        FROM notifications n
        LEFT JOIN notification_reads r
          ON r.notification_id = n.id
          AND r.user_email = ?
        ORDER BY n.created_at DESC, n.id DESC
        LIMIT ? OFFSET ?
        """,
        [current_user["email"], limit, offset]
    )

    return [
        {
            "id": row[0],
            "title": row[1],
            "body": row[2],
            "created_at": row[3],
            "read": bool(row[4])
        }
        for row in result.rows
    ]



# --------------------------------------------------
# USER: MARK ONE NOTIFICATION READ
# --------------------------------------------------

@app.post("/api/notifications/{notification_id}/read")
def mark_notification_read(
    notification_id: int,
    current_user: dict = Depends(get_current_user)
):
    exists = client.execute(
        "SELECT id FROM notifications WHERE id = ?",
        [notification_id]
    )

    if not exists.rows:
        raise HTTPException(404, "Notification not found")

    client.execute(
        """
        INSERT OR IGNORE INTO notification_reads
            (notification_id, user_email)
        VALUES (?, ?)
        """,
        [notification_id, current_user["email"]]
    )

    return {"ok": True}


# --------------------------------------------------
# USER: MARK ALL NOTIFICATIONS READ
# --------------------------------------------------

@app.post("/api/notifications/read-all")
def mark_all_notifications_read(
    current_user: dict = Depends(get_current_user)
):
    client.execute(
        """
        INSERT OR IGNORE INTO notification_reads
            (notification_id, user_email)
        SELECT id, ? FROM notifications
        """,
        [current_user["email"]]
    )

    return {"ok": True}
