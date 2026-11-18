"""Local-only A/B listening and independent subjective ratings."""
import json
import os
import tempfile
from pathlib import Path
from typing import Literal

from fastapi import APIRouter, HTTPException
from fastapi.responses import FileResponse, HTMLResponse
from pydantic import BaseModel

from app.config import settings

router = APIRouter(prefix="/ab", tags=["local A/B evaluation"])
BASE = Path("analysis/ab-preview-v1")


def preview_dir() -> Path:
    if settings.environment != "local":
        raise HTTPException(404, "A/B previews only available locally")
    return (settings.storage_dir / BASE).resolve()


def read_report() -> tuple[Path, dict]:
    folder = preview_dir()
    try:
        data = json.loads((folder / "report.json").read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        raise HTTPException(404, "A/B report missing or invalid") from exc
    items = data.get("items") if isinstance(data, dict) else None
    if not isinstance(items, list) or not items:
        raise HTTPException(422, "Invalid A/B report")
    seen = set()
    for item in items:
        if not isinstance(item, dict) or not isinstance(item.get("episode"), str):
            raise HTTPException(422, "Invalid A/B item")
        if item["episode"] in seen:
            raise HTTPException(422, "Duplicate A/B episode")
        seen.add(item["episode"])
        for field in ("original", "preview"):
            name = item.get(field)
            if not isinstance(name, str) or Path(name).name != name or not name.endswith(".wav"):
                raise HTTPException(422, "Invalid A/B audio name")
    return folder, data


def read_ratings(folder: Path) -> dict:
    path = folder / "ratings.json"
    if not path.exists():
        return {}
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        raise HTTPException(422, "Ratings file is invalid") from exc
    if not isinstance(value, dict):
        raise HTTPException(422, "Ratings must be an object")
    return value


def atomic_write(path: Path, data: dict) -> None:
    temporary = None
    try:
        with tempfile.NamedTemporaryFile("w", encoding="utf-8", dir=path.parent,
                                         prefix=".ab-ratings-", suffix=".tmp", delete=False) as handle:
            temporary = handle.name
            json.dump(data, handle, ensure_ascii=False, indent=2)
            handle.write("\n")
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, path)
    finally:
        if temporary and os.path.exists(temporary):
            os.unlink(temporary)


class Rating(BaseModel):
    verdict: Literal["better", "worse", "unclear"]


@router.get("", response_class=HTMLResponse)
def page():
    read_report()
    return HTMLResponse(PAGE)


@router.get("/items")
def items():
    folder, data = read_report()
    ratings = read_ratings(folder)
    return {"items": [{**item, "rating": ratings.get(item["episode"])} for item in data["items"]],
            "warning": data.get("warning", "")}


@router.get("/audio/{filename}")
def audio(filename: str):
    folder, data = read_report()
    allowed = {item[key] for item in data["items"] for key in ("original", "preview")}
    if filename not in allowed:
        raise HTTPException(404, "Unknown preview file")
    path = (folder / filename).resolve()
    if not path.is_relative_to(folder) or not path.is_file():
        raise HTTPException(404, "Preview audio missing")
    return FileResponse(path, media_type="audio/wav", filename=filename)


@router.put("/ratings/{episode}")
def rate(episode: str, payload: Rating):
    folder, data = read_report()
    if episode not in {item["episode"] for item in data["items"]}:
        raise HTTPException(404, "Unknown A/B episode")
    ratings = read_ratings(folder)
    ratings[episode] = payload.verdict
    atomic_write(folder / "ratings.json", ratings)
    return {"episode": episode, "rating": payload.verdict}


PAGE = """<!doctype html>
<html lang="ru"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>CrowdClean · A/B</title>
<style>
body{font:16px system-ui;background:#111827;color:#f9fafb;max-width:820px;margin:35px auto;padding:0 20px}
h1{font-size:28px}.card{background:#1f2937;padding:24px;border-radius:16px;margin:20px 0}
audio{width:100%;margin:10px 0 20px}button{padding:12px 17px;margin:5px;border:0;border-radius:9px;cursor:pointer;font-weight:650}
nav{display:flex;justify-content:space-between;align-items:center}.better{background:#86efac}.worse{background:#fca5a5}.unclear{background:#d1d5db}
small{color:#9ca3af}#error{color:#fca5a5}label{display:block;margin-top:15px}
</style></head><body>
<h1>CrowdClean · A/B-прослушивание</h1>
<p>Сравни два фрагмента. Обработанный вариант приглушает всю музыку вместе с голосом — это эксперимент, не готовая очистка.</p>
<div class="card"><nav><button id="prev">← Назад</button><strong id="progress">Загрузка…</strong><button id="next">Далее →</button></nav>
<h2 id="name"></h2><p id="times"></p>
<label><strong>A — Оригинал</strong><audio id="original" controls preload="none"></audio></label>
<label><strong>B — Приглушённый</strong><audio id="preview" controls preload="none"></audio></label>
<p><small>Плееры синхронизируются по позиции при переключении воспроизведения.</small></p>
<p>Какой результат по сохранению музыки и уменьшению выкрика?</p>
<button class="better" data-verdict="better">B лучше</button>
<button class="worse" data-verdict="worse">B хуже</button>
<button class="unclear" data-verdict="unclear">Не уверен</button>
<p id="status"></p><p id="error" role="alert"></p></div>
<script>
let items=[],index=0;
const el=id=>document.getElementById(id);
function render(){
 const item=items[index];if(!item)return;
 el("name").textContent=item.episode;
 el("times").textContent="В миксе: "+item.start.toFixed(1)+"–"+item.end.toFixed(1)+" с";
 for(const field of ["original","preview"]){
  const player=el(field);player.pause();player.src="/ab/audio/"+encodeURIComponent(item[field]);player.load();
 }
 el("status").textContent=item.rating?"Оценка сохранена: "+item.rating:"Оценка пока не задана";
 el("progress").textContent=items.filter(x=>x.rating).length+" / "+items.length+" оценено · "+(index+1)+" / "+items.length;
 el("prev").disabled=index===0;el("next").disabled=index===items.length-1;
 el("error").textContent="";
}
for(const field of ["original","preview"]){
 const other=field==="original"?"preview":"original";
 el(field).addEventListener("play",()=>{
  const previous=el(other);previous.pause();
  if(Number.isFinite(previous.currentTime))el(field).currentTime=previous.currentTime;
 });
}
document.querySelectorAll("[data-verdict]").forEach(button=>button.onclick=async()=>{
 const item=items[index];
 try{
  const response=await fetch("/ab/ratings/"+encodeURIComponent(item.episode),{
   method:"PUT",headers:{"Content-Type":"application/json"},body:JSON.stringify({verdict:button.dataset.verdict})});
  if(!response.ok)throw Error("HTTP "+response.status);
  const saved=await response.json();item.rating=saved.rating;render();
  if(index<items.length-1){index++;render();}
 }catch(error){el("error").textContent="Не удалось сохранить оценку: "+error.message;}
});
el("prev").onclick=()=>{index--;render()};
el("next").onclick=()=>{index++;render()};
fetch("/ab/items").then(response=>{if(!response.ok)throw Error("HTTP "+response.status);return response.json()})
.then(data=>{items=data.items;render()}).catch(error=>el("error").textContent=error.message);
</script></body></html>"""
