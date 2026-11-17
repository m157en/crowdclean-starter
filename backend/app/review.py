"""Local-only review of generated WAV candidates; never edits source audio."""
import json
import os
import tempfile
from pathlib import Path

from fastapi import APIRouter, HTTPException
from fastapi.responses import FileResponse, HTMLResponse
from pydantic import BaseModel, Literal

from app.config import settings

router = APIRouter(prefix="/review", tags=["local review"])
REVIEW_FOLDER = Path("analysis/review/threshold-03")


def review_dir() -> Path:
    if settings.environment != "local":
        raise HTTPException(404, "Review UI is only available in local environment")
    return (settings.storage_dir / REVIEW_FOLDER).resolve()


def read_manifest() -> tuple[Path, list[dict]]:
    directory = review_dir()
    path = directory / "manifest.json"
    try:
        items = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        raise HTTPException(404, "Review manifest not found or invalid") from exc
    if not isinstance(items, list):
        raise HTTPException(422, "Review manifest must be an array")
    for item in items:
        if not isinstance(item, dict) or not isinstance(item.get("file"), str):
            raise HTTPException(422, "Invalid manifest item")
        name = item["file"]
        if Path(name).name != name or not name.startswith("review-") or not name.endswith(".wav"):
            raise HTTPException(422, "Invalid audio filename")
    return path, items


class ReviewDecision(BaseModel):
    decision: Literal["pending", "keep", "remove"]


@router.get("", response_class=HTMLResponse)
def review_page():
    review_dir()
    return HTMLResponse(PAGE)


@router.get("/items")
def review_items():
    _, items = read_manifest()
    return items


@router.get("/audio/{filename}")
def review_audio(filename: str):
    directory = review_dir()
    _, items = read_manifest()
    if filename not in {item["file"] for item in items}:
        raise HTTPException(404, "Unknown review clip")
    path = (directory / filename).resolve()
    if not path.is_relative_to(directory) or not path.is_file():
        raise HTTPException(404, "Audio clip missing")
    return FileResponse(path, media_type="audio/wav", filename=filename)


@router.patch("/items/{filename}")
def set_review_decision(filename: str, payload: ReviewDecision):
    path, items = read_manifest()
    match = next((item for item in items if item["file"] == filename), None)
    if match is None:
        raise HTTPException(404, "Unknown review clip")
    match["decision"] = payload.decision
    # Atomic replace avoids partially written JSON if interrupted.
    temp_name = None
    try:
        with tempfile.NamedTemporaryFile("w", encoding="utf-8", dir=path.parent, prefix=".manifest-", suffix=".tmp", delete=False) as handle:
            temp_name = handle.name
            json.dump(items, handle, ensure_ascii=False, indent=2)
            handle.write("\n")
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temp_name, path)
    finally:
        if temp_name and os.path.exists(temp_name):
            os.unlink(temp_name)
    return match


PAGE = """<!doctype html>
<html lang="ru"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1">
<title>CrowdClean · Review</title>
<style>
body{font:16px system-ui;background:#111827;color:#f9fafb;max-width:850px;margin:36px auto;padding:0 20px}
header{display:flex;justify-content:space-between;align-items:center;gap:12px}h1{font-size:28px}
.card{background:#1f2937;border-radius:16px;padding:24px;margin-top:20px}
button{padding:12px 18px;margin:6px;border:0;border-radius:9px;cursor:pointer;font-weight:700}
.keep{background:#86efac}.remove{background:#fca5a5}.pending{background:#d1d5db}
nav{display:flex;justify-content:space-between;align-items:center}
audio{width:100%;margin:18px 0}small{color:#9ca3af}#error{color:#fca5a5}
</style></head><body>
<header><h1>CrowdClean · Review</h1><strong id="progress">Загрузка…</strong></header>
<p>Прослушай эпизод и выбери KEEP (музыка) или REMOVE (DJ-выкрик). Оригинал не меняется.</p>
<div class="card">
<nav><button id="prev">← Назад</button><span id="position"></span><button id="next">Далее →</button></nav>
<h2 id="filename"></h2><p id="timing"></p><audio id="player" controls preload="none"></audio>
<div><button class="keep" data-decision="keep">KEEP</button><button class="remove" data-decision="remove">REMOVE</button><button class="pending" data-decision="pending">Сбросить</button></div>
<p id="decision"></p><p id="error" role="alert"></p>
</div>
<script>
let items=[],index=0;
const el=id=>document.getElementById(id);
function render(){
 const item=items[index];if(!item)return;
 el("position").textContent=(index+1)+" / "+items.length;
 el("filename").textContent=item.file;
 el("timing").textContent="Время: "+item.start.toFixed(1)+"–"+item.end.toFixed(1)+" с · Интервалов: "+item.detected_intervals;
 el("player").src="/review/audio/"+encodeURIComponent(item.file);
 el("decision").textContent="Решение: "+item.decision.toUpperCase();
 el("progress").textContent=items.filter(x=>x.decision!=="pending").length+" / "+items.length+" размечено";
 el("prev").disabled=index===0;el("next").disabled=index===items.length-1;
 el("error").textContent="";
}
async function decide(decision){
 const item=items[index];
 try{
 const response=await fetch("/review/items/"+encodeURIComponent(item.file),{method:"PATCH",headers:{"Content-Type":"application/json"},body:JSON.stringify({decision})});
 if(!response.ok)throw Error("Ошибка сохранения: HTTP "+response.status);
 items[index]=await response.json();render();
 }catch(e){el("error").textContent=e.message;}
}
el("prev").onclick=()=>{index--;render()};
el("next").onclick=()=>{index++;render()};
document.querySelectorAll("[data-decision]").forEach(b=>b.onclick=()=>decide(b.dataset.decision));
fetch("/review/items").then(r=>{if(!r.ok)throw Error("HTTP "+r.status);return r.json()}).then(data=>{items=data;render()}).catch(e=>el("error").textContent=e.message);
</script></body></html>"""
