"""Generate an offline, self-contained index for comparing local CrowdClean WAVs.

No web server, network requests, upload, or mutations to audio. The HTML file
uses relative local WAV paths; it is intended to be opened on the same Mac.
"""
import argparse
import html
import json
from pathlib import Path
from urllib.parse import quote


def export_review(folder: Path, version: str = "v3") -> Path:
    if version not in ("v3", "v4"):
        raise ValueError("Unsupported review version")
    folder = folder.resolve()
    report = json.loads((folder / "report.json").read_text(encoding="utf-8"))
    items = report.get("items")
    if not isinstance(items, list) or not items:
        raise ValueError("Report is empty or malformed")
    output = folder / f"listen-{version}.html"
    if output.exists():
        raise FileExistsError(output)
    groups = {}
    for item in items:
        if not isinstance(item, dict):
            raise ValueError("Invalid A/B item")
        episode = item["source_episode"]
        if not isinstance(episode, str) or not episode.startswith("review-"):
            raise ValueError("Invalid episode")
        for field in ("original", "preview"):
            name = item[field]
            if not isinstance(name, str) or Path(name).name != name or not name.endswith(".wav"):
                raise ValueError("Unsafe audio path")
            if not (folder / name).is_file():
                raise FileNotFoundError(folder / name)
        groups.setdefault(episode, []).append(item)
    styles = """
body{font:16px -apple-system,BlinkMacSystemFont,system-ui,sans-serif;background:#111827;color:#fafafa;max-width:950px;margin:30px auto;padding:0 18px}
section{background:#1f2937;padding:20px;border-radius:14px;margin:18px 0}
h1{font-size:1.7rem}h2{font-size:1.25rem}p{line-height:1.5}
audio{display:block;width:100%;margin:8px 0 22px}
label{display:block;font-weight:650}small{color:#cbd5e1}
"""
    parts = [
        '<!doctype html><html lang="ru"><head><meta charset="utf-8">',
        '<meta name="viewport" content="width=device-width,initial-scale=1">',
        f'<title>CrowdClean {version} — private A/B</title>',
        '<style>'+styles+'</style></head><body>',
        f'<h1>CrowdClean · {version}: сравнение музыки и удаления голоса DJ</h1>',
        '<p>Локальное прослушивание. Файлы не отправляются в интернет. '
        'Сравнивай одинаковые фрагменты при одинаковой громкости устройства. '
        'Эти методы экспериментальные и могут повредить элементы музыки.</p>'
    ]
    for episode, variants in groups.items():
        original_name = variants[0]["original"]
        parts.append('<section><h2>'+html.escape(episode)+'</h2>')
        parts.append('<label>Оригинал</label><audio controls preload="none" src="'+quote(original_name)+'"></audio>')
        for item in variants:
            method = str(item["method"])
            parts.append('<label>Вариант: '+html.escape(method)+'</label>')
            parts.append('<audio controls preload="none" src="'+quote(item["preview"])+'"></audio>')
        parts.append('<small>Слушай: начало речи, бас, ударные, мелодию, переход и конец обработки.</small></section>')
    parts.append('</body></html>')
    # Exclusive create: never silently replace a completed review index.
    with output.open("x", encoding="utf-8") as handle:
        handle.write("\n".join(parts))
    return output


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--folder", required=True, type=Path)
    args = p.parse_args()
    print(export_review(args.folder))


if __name__ == "__main__":
    main()
