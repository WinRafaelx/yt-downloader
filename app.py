from __future__ import annotations

import shutil
import uuid
from pathlib import Path

from flask import Flask, jsonify, render_template, request, send_file
from werkzeug.utils import secure_filename
from yt_dlp import YoutubeDL


BASE_DIR = Path(__file__).resolve().parent
DOWNLOAD_DIR = BASE_DIR / "downloads"
ALLOWED_FORMATS = {"mp3", "wav", "mp4"}

app = Flask(__name__)
app.config["MAX_CONTENT_LENGTH"] = 1024
DOWNLOAD_DIR.mkdir(exist_ok=True)


def build_options(output_format: str, output_template: str) -> dict:
    if output_format in {"mp3", "wav"}:
        return {
            "format": "bestaudio/best",
            "outtmpl": output_template,
            "noplaylist": True,
            "postprocessors": [
                {
                    "key": "FFmpegExtractAudio",
                    "preferredcodec": output_format,
                    "preferredquality": "192",
                }
            ],
        }

    return {
        "format": "bestvideo[ext=mp4]+bestaudio[ext=m4a]/best[ext=mp4]/best",
        "merge_output_format": "mp4",
        "outtmpl": output_template,
        "noplaylist": True,
    }


def download_media(url: str, output_format: str) -> Path:
    job_id = uuid.uuid4().hex
    output_template = str(DOWNLOAD_DIR / f"{job_id}.%(ext)s")
    options = build_options(output_format, output_template)

    with YoutubeDL(options) as ydl:
        info = ydl.extract_info(url, download=True)

    downloaded = sorted(DOWNLOAD_DIR.glob(f"{job_id}.*"), key=lambda path: path.stat().st_mtime)
    matching = [path for path in downloaded if path.suffix.lower() == f".{output_format}"]
    if not matching:
        raise RuntimeError(f"Could not create a .{output_format} file.")

    title = secure_filename(info.get("title") or f"youtube-download-{job_id}")
    final_path = DOWNLOAD_DIR / f"{title}.{output_format}"
    counter = 1
    while final_path.exists():
        final_path = DOWNLOAD_DIR / f"{title}-{counter}.{output_format}"
        counter += 1

    shutil.move(str(matching[-1]), final_path)
    for leftover in downloaded:
        if leftover.exists():
            leftover.unlink()

    return final_path


def enhanced_request() -> bool:
    return request.headers.get("X-Requested-With") == "fetch"


def download_error(message: str, status_code: int):
    if enhanced_request():
        return jsonify({"error": message}), status_code

    return (
        render_template(
            "index.html",
            error=message,
            url=request.form.get("url", ""),
            selected=request.form.get("format", ""),
        ),
        status_code,
    )


@app.get("/")
def index():
    return render_template("index.html")


@app.post("/download")
def download():
    url = request.form.get("url", "").strip()
    output_format = request.form.get("format", "").strip().lower()

    if not url:
        return download_error("Paste a YouTube URL first.", 400)

    if output_format not in ALLOWED_FORMATS:
        return download_error("Choose MP3, WAV, or MP4.", 400)

    try:
        media_path = download_media(url, output_format)
    except Exception as exc:
        return download_error(str(exc), 500)

    return send_file(media_path, as_attachment=True, download_name=media_path.name)


if __name__ == "__main__":
    app.run(host="127.0.0.1", port=5000, debug=True)
