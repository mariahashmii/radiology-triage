import io
import base64
from datetime import datetime
import uuid
from fastapi import FastAPI, UploadFile, File, HTTPException
from fastapi.staticfiles import StaticFiles
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.middleware.cors import CORSMiddleware
import uvicorn
from PIL import Image
import numpy as np

from model_utils import predict_xray
from heatmap_utils import generate_heatmap
from clinical_reasoning import calculate_risk
from metadata_utils import get_patient_metadata
from queue_utils import get_urgency

app = FastAPI(title="NeuroScan Edge API")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.mount("/static", StaticFiles(directory="static"), name="static")

# ---------------------------------------------------------------------------
# In-memory stores
# ---------------------------------------------------------------------------
scan_history = []       # list of scan metadata dicts (no base64 images)
scan_images = {}        # scan_id -> {"heatmap_base64": ..., "original_base64": ...}

# ---------------------------------------------------------------------------
# HTML page routes
# ---------------------------------------------------------------------------

@app.get("/", response_class=HTMLResponse)
async def read_root():
    with open("static/landing_experience.html", "r", encoding="utf-8") as f:
        return f.read()

@app.get("/command_center", response_class=HTMLResponse)
async def command_center():
    with open("static/ai_command_center.html", "r", encoding="utf-8") as f:
        return f.read()

@app.get("/queue", response_class=HTMLResponse)
async def queue_dashboard():
    with open("static/mission_control_queue.html", "r", encoding="utf-8") as f:
        return f.read()

@app.get("/dossier", response_class=HTMLResponse)
async def dossier():
    with open("static/clinical_dossier.html", "r", encoding="utf-8") as f:
        return f.read()

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def image_to_base64(img_array):
    img = Image.fromarray(img_array)
    buffered = io.BytesIO()
    img.save(buffered, format="PNG")
    return base64.b64encode(buffered.getvalue()).decode("utf-8")


def make_serializable(obj):
    if isinstance(obj, np.generic):
        return obj.item()
    elif isinstance(obj, dict):
        return {k: make_serializable(v) for k, v in obj.items()}
    elif isinstance(obj, (list, tuple)):
        return [make_serializable(v) for v in obj]
    return obj

# ---------------------------------------------------------------------------
# API endpoints
# ---------------------------------------------------------------------------

@app.post("/api/analyze")
async def analyze_xray(file: UploadFile = File(...)):
    try:
        contents = await file.read()
        file_obj = io.BytesIO(contents)
        file_obj.name = file.filename

        try:
            metadata = get_patient_metadata(file.filename) or {}
        except FileNotFoundError:
            metadata = {}
        age = metadata.get("age")
        gender = metadata.get("gender")
        view_position = metadata.get("view_position")
        patient_id = metadata.get("patient_id") or file.filename

        file_obj.seek(0)
        prediction = predict_xray(file_obj)

        selected_findings = prediction.get("selected_findings", [])
        raw_scores = prediction.get("selected_scores", [])
        selected_scores = [(s[0], float(s[1])) for s in raw_scores]
        confidences = [s for _, s in selected_scores] if selected_scores else []
        top_finding = prediction.get("display_label", "No Finding")
        top_score = float(prediction.get("display_score", 0.0))

        risk_score, urgency_simple, reason = calculate_risk(
            selected_findings, confidences,
            age=age, gender=gender, view_position=view_position,
        )
        risk_score = float(risk_score)

        urgency = get_urgency(
            selected_findings, top_score,
            age=age, gender=gender, view_position=view_position,
        )

        file_obj.seek(0)
        heatmap_array = generate_heatmap(file_obj)
        heatmap_b64 = image_to_base64(heatmap_array)

        file_obj.seek(0)
        orig_img = Image.open(file_obj).convert("RGB")
        orig_buffered = io.BytesIO()
        orig_img.save(orig_buffered, format="JPEG")
        orig_b64 = base64.b64encode(orig_buffered.getvalue()).decode("utf-8")

        heatmap_base64 = f"data:image/png;base64,{heatmap_b64}"
        original_base64 = f"data:image/jpeg;base64,{orig_b64}"

        response_dict = {
            "patient_id": patient_id, "filename": file.filename,
            "age": age, "gender": gender, "view_position": view_position,
            "top_finding": top_finding, "top_score": top_score,
            "selected_findings": selected_findings, "selected_scores": selected_scores,
            "risk_score": risk_score, "urgency": urgency, "reason": reason,
            "heatmap_base64": heatmap_base64,
            "original_base64": original_base64,
        }

        # ---- persist to in-memory history --------------------------------
        scan_id = str(uuid.uuid4())[:8]

        history_entry = {
            "scan_id": scan_id,
            "patient_id": patient_id,
            "filename": file.filename,
            "age": age,
            "gender": gender,
            "view_position": view_position,
            "top_finding": top_finding,
            "top_score": top_score,
            "selected_findings": list(selected_findings),
            "selected_scores": list(selected_scores),
            "risk_score": risk_score,
            "urgency": urgency,
            "reason": reason,
            "timestamp": datetime.now().isoformat(),
        }
        scan_history.append(make_serializable(history_entry))

        scan_images[scan_id] = {
            "heatmap_base64": heatmap_base64,
            "original_base64": original_base64,
        }

        # also include scan_id in the response so the frontend can use it
        response_dict["scan_id"] = scan_id

        return JSONResponse(make_serializable(response_dict))
    except Exception as e:
        import traceback
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/queue")
async def get_scan_queue():
    sorted_history = sorted(
        scan_history,
        key=lambda s: s.get("risk_score", 0),
        reverse=True,
    )

    critical_count = sum(
        1 for s in scan_history if "HIGH" in (s.get("urgency") or "").upper()
    )
    priority_count = sum(
        1 for s in scan_history if "MEDIUM" in (s.get("urgency") or "").upper()
    )
    routine_count = sum(
        1 for s in scan_history if "LOW" in (s.get("urgency") or "").upper()
    )

    return JSONResponse(make_serializable({
        "scans": sorted_history,
        "critical_count": critical_count,
        "priority_count": priority_count,
        "routine_count": routine_count,
    }))


@app.get("/api/scan/{scan_id}")
async def get_scan(scan_id: str):
    entry = next((s for s in scan_history if s.get("scan_id") == scan_id), None)
    if entry is None:
        raise HTTPException(status_code=404, detail="Scan not found")

    images = scan_images.get(scan_id, {})
    full_data = {**entry, **images}

    return JSONResponse(make_serializable(full_data))


if __name__ == "__main__":
    uvicorn.run("api:app", host="0.0.0.0", port=8000, reload=True)
