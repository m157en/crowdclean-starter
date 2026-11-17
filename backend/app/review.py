"""Local-only review of generated WAV candidates; never edits source audio."""
import json
import os
import tempfile
import math
from pathlib import Path

from fastapi import APIRouter, HTTPException
from fastapi.responses import FileResponse, HTMLResponse
from typing import Literal
from pydantic import BaseModel, model_validator

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



class Boundary(BaseModel):
    start: float
    end: float

    @model_validator(mode="after")
    def check_order(self):
        if not (math.isfinite(self.start) and math.isfinite(self.end) and self.start < self.end):
            raise ValueError("Invalid boundary")
        return self


@router.put("/items/{filename}/boundary")
def save_boundary(filename: str, payload: Boundary):
    path, items = read_manifest()
    item = next((x for x in items if x["file"] == filename), None)
    if item is None:
        raise HTTPException(404, "Unknown review clip")
    if item["decision"] != "remove":
        raise HTTPException(409, "Only REMOVE clips can have boundaries")
    if not (item["start"] <= payload.start < payload.end <= item["end"]):
        raise HTTPException(422, "Boundary outside review clip")
    item["precise_boundary"] = {"start": payload.start, "end": payload.end}
    atomic_manifest(path, items)
    return item


def atomic_manifest(path: Path, items: list[dict]):
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


@router.get("", response_class=HTMLResponse)
def review_page():
    review_dir()
    return HTMLResponse(PAGE)


@router.get("/items")
def review_items():
    _, items = read_manifest()
    return [item for item in items if item.get("decision") == "remove"]


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
    if payload.decision != "remove":
        match.pop("precise_boundary", None)
    atomic_manifest(path, items)
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
<p>Показаны только подтверждённые REMOVE-эпизоды. Уточни границы выкрика внутри каждого. KEEP-эпизоды сохранены отдельно.</p>
<div class="card">
<nav><button id="prev">← Назад</button><span id="position"></span><button id="next">Далее →</button></nav>
<h2 id="filename"></h2><p id="timing"></p><audio id="player" controls preload="none"></audio>
<div><button class="keep" data-decision="keep">KEEP</button><button class="remove" data-decision="remove">REMOVE</button><button class="pending" data-decision="pending">Сбросить</button></div>
<p id="decision"></p>
<section id="boundarySection" hidden>
<p>Границы выкрика (секунды от начала этого фрагмента, можно целыми числами)</p>
<label>Начало <input id="start" type="number" min="0" step="1"></label>
<button id="markStart">Начало = позиция плеера</button>
<p><label>Конец <input id="end" type="number" min="0" step="1"></label>
<button id="markEnd">Конец = позиция плеера</button></p>
<button id="preview">Прослушать диапазон</button>
<button id="saveBoundary">Сохранить границы</button>
<p id="boundaryStatus"></p></section><p id="error" role="alert"></p>
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
 el("boundarySection").hidden=item.decision!=="remove";
 el("start").value=item.precise_boundary ? Math.round((item.precise_boundary.start-item.start)*100)/100 : "";
 el("end").value=item.precise_boundary ? Math.round((item.precise_boundary.end-item.start)*100)/100 : "";
 el("boundaryStatus").textContent=item.precise_boundary?"Границы сохранены":"Границы не заданы";
 el("progress").textContent=items.filter(x=>x.precise_boundary).length+" / "+items.length+" границ уточнено";
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

el("markStart").onclick=()=>{el("start").value=Math.round(el("player").currentTime)};
el("markEnd").onclick=()=>{el("end").value=(items[index].start+el("player").currentTime).toFixed(2)};
el("preview").onclick=()=>{
 const item=items[index],start=Number(el("start").value),end=Number(el("end").value);
 if(!el("start").value||!el("end").value||start<0||end>item.end-item.start||start>=end){el("error").textContent="Проверь границы";return;}
 const player=el("player");player.currentTime=start;player.play();
 const stop=()=>{if(player.currentTime>=end){player.pause();player.removeEventListener("timeupdate",stop)}};
 player.addEventListener("timeupdate",stop);
};
el("saveBoundary").onclick=async()=>{
 const item=items[index],start=Number(el("start").value),end=Number(el("end").value);
 if(!el("start").value||!el("end").value||!Number.isFinite(start)||!Number.isFinite(end)||start<0||end>item.end-item.start||start>=end){el("error").textContent="Некорректные границы";return;}
 try{
 const response=await fetch("/review/items/"+encodeURIComponent(item.file)+"/boundary",{method:"PUT",headers:{"Content-Type":"application/json"},body:JSON.stringify({start:item.start+start,end:item.start+end})});
 if(!response.ok)throw Error("HTTP "+response.status);
 items[index]=await response.json();render();
 }catch(e){el("error").textContent=e.message}
};
el("prev").onclick=()=>{index--;render()};
el("next").onclick=()=>{index++;render()};
document.querySelectorAll("[data-decision]").forEach(b=>b.onclick=()=>decide(b.dataset.decision));
fetch("/review/items").then(r=>{if(!r.ok)throw Error("HTTP "+r.status);return r.json()}).then(data=>{items=data;if(!items.length){el("progress").textContent="Нет REMOVE-эпизодов";return;}render()}).catch(e=>el("error").textContent=e.message);
</script></body></html>"""
