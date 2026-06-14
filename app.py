from __future__ import annotations

import json
import shutil
import subprocess
import threading
import uuid
from pathlib import Path

from flask import Flask, abort, jsonify, render_template, request, send_file
from werkzeug.utils import secure_filename
from yt_dlp import YoutubeDL


BASE_DIR = Path(__file__).resolve().parent
DOWNLOAD_DIR = BASE_DIR / "downloads"
ALLOWED_FORMATS = {"mp3", "wav", "mp4"}
SAFE_MP4_FORMAT = (
    "bestvideo[ext=mp4][vcodec^=avc1]+bestaudio[ext=m4a][acodec^=mp4a]/"
    "best[ext=mp4][vcodec^=avc1][acodec^=mp4a]/"
    "bestvideo[ext=mp4]+bestaudio[ext=m4a]/best[ext=mp4]/best"
)

app = Flask(__name__)
app.config["MAX_CONTENT_LENGTH"] = 1024
DOWNLOAD_DIR.mkdir(exist_ok=True)

jobs: dict[str, dict] = {}
jobs_lock = threading.Lock()


def build_options(
    output_format: str,
    output_template: str,
    progress_hook=None,
    postprocessor_hook=None,
) -> dict:
    if output_format in {"mp3", "wav"}:
        options = {
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
    else:
        options = {
            "format": SAFE_MP4_FORMAT,
            "merge_output_format": "mp4",
            "outtmpl": output_template,
            "noplaylist": True,
        }

    if progress_hook:
        options["progress_hooks"] = [progress_hook]
    if postprocessor_hook:
        options["postprocessor_hooks"] = [postprocessor_hook]

    return options


def media_codecs(path: Path) -> tuple[str | None, str | None]:
    command = [
        "ffprobe",
        "-v",
        "error",
        "-show_entries",
        "stream=codec_type,codec_name",
        "-of",
        "json",
        str(path),
    ]
    result = subprocess.run(command, check=True, capture_output=True, text=True)
    streams = json.loads(result.stdout).get("streams", [])
    video_codec = next((stream["codec_name"] for stream in streams if stream.get("codec_type") == "video"), None)
    audio_codec = next((stream["codec_name"] for stream in streams if stream.get("codec_type") == "audio"), None)

    return video_codec, audio_codec


def ensure_safe_mp4(path: Path, conversion_hook=None) -> Path:
    video_codec, audio_codec = media_codecs(path)
    if video_codec == "h264" and audio_codec == "aac":
        return path

    if conversion_hook:
        conversion_hook()

    converted_path = path.with_name(f"{path.stem}-{uuid.uuid4().hex}-quicktime{path.suffix}")
    command = [
        "ffmpeg",
        "-y",
        "-i",
        str(path),
        "-c:v",
        "libx264",
        "-pix_fmt",
        "yuv420p",
        "-preset",
        "medium",
        "-crf",
        "20",
        "-c:a",
        "aac",
        "-b:a",
        "160k",
        "-movflags",
        "+faststart",
        str(converted_path),
    ]

    try:
        subprocess.run(command, check=True, capture_output=True, text=True)
        path.unlink()
        converted_path.replace(path)
    except Exception:
        if converted_path.exists():
            converted_path.unlink()
        raise

    return path


def download_media(
    url: str,
    output_format: str,
    progress_hook=None,
    postprocessor_hook=None,
    job_id: str | None = None,
) -> Path:
    job_id = job_id or uuid.uuid4().hex
    output_template = str(DOWNLOAD_DIR / f"{job_id}.%(ext)s")
    options = build_options(output_format, output_template, progress_hook, postprocessor_hook)

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

    if output_format == "mp4":
        conversion_hook = None
        if postprocessor_hook:
            conversion_hook = lambda: postprocessor_hook({"status": "started"})
        final_path = ensure_safe_mp4(final_path, conversion_hook)

    return final_path


def update_job(job_id: str, **updates) -> None:
    with jobs_lock:
        job = jobs.get(job_id)
        if job:
            job.update(updates)


def public_job(job_id: str) -> dict:
    with jobs_lock:
        job = jobs.get(job_id)
        if not job:
            abort(404)

        return {
            "id": job_id,
            "status": job["status"],
            "progress": job["progress"],
            "message": job["message"],
            "error": job.get("error"),
            "filename": job.get("filename"),
            "download_url": f"/jobs/{job_id}/file" if job["status"] == "complete" else None,
        }


def format_progress_message(data: dict) -> tuple[int, str]:
    downloaded = data.get("downloaded_bytes") or 0
    total = data.get("total_bytes") or data.get("total_bytes_estimate") or 0

    if total:
        progress = min(99, int(downloaded / total * 100))
        return progress, f"Downloading media... {progress}%"

    return 0, "Downloading media..."


def run_download_job(job_id: str, url: str, output_format: str) -> None:
    def progress_hook(data: dict) -> None:
        status = data.get("status")
        if status == "downloading":
            progress, message = format_progress_message(data)
            update_job(job_id, status="downloading", progress=progress, message=message)
        elif status == "finished":
            update_job(job_id, status="processing", progress=99, message="Processing file...")

    def postprocessor_hook(data: dict) -> None:
        if data.get("status") == "started":
            update_job(job_id, status="processing", progress=99, message="Converting file...")

    try:
        update_job(job_id, status="starting", progress=0, message="Reading video info...")
        media_path = download_media(url, output_format, progress_hook, postprocessor_hook, job_id)
    except Exception as exc:
        update_job(job_id, status="error", progress=0, message="Download failed.", error=str(exc))
        return

    update_job(
        job_id,
        status="complete",
        progress=100,
        message="Download complete.",
        file_path=str(media_path),
        filename=media_path.name,
    )


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


@app.post("/jobs")
def create_job():
    url = request.form.get("url", "").strip()
    output_format = request.form.get("format", "").strip().lower()

    if not url:
        return jsonify({"error": "Paste a YouTube URL first."}), 400

    if output_format not in ALLOWED_FORMATS:
        return jsonify({"error": "Choose MP3, WAV, or MP4."}), 400

    job_id = uuid.uuid4().hex
    with jobs_lock:
        jobs[job_id] = {
            "status": "queued",
            "progress": 0,
            "message": "Queued download...",
            "error": None,
            "file_path": None,
            "filename": None,
        }

    thread = threading.Thread(target=run_download_job, args=(job_id, url, output_format), daemon=True)
    thread.start()

    return jsonify(public_job(job_id)), 202


@app.get("/jobs/<job_id>")
def job_status(job_id: str):
    return jsonify(public_job(job_id))


@app.get("/jobs/<job_id>/file")
def job_file(job_id: str):
    with jobs_lock:
        job = jobs.get(job_id)
        if not job:
            abort(404)
        if job["status"] != "complete" or not job.get("file_path"):
            abort(409)
        media_path = Path(job["file_path"])
        filename = job.get("filename") or media_path.name

    return send_file(media_path, as_attachment=True, download_name=filename)


if __name__ == "__main__":
    app.run(host="127.0.0.1", port=5001, debug=True)
