# Local YouTube Downloader

Simple local web app for downloading a YouTube URL as MP3, WAV, or MP4.

Use it only for videos you own, have permission to download, or where downloading is allowed.

## Setup

```bash
cd /Users/cielsensei/Raf_dev/yt_downloader
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
python app.py
```

Then open:

```text
http://127.0.0.1:5001
```

## Notes

- MP3 and WAV need `ffmpeg`.
- MP4 prefers H.264 video with AAC audio for broad compatibility, including QuickTime.
- Completed downloads are kept in `yt_downloader/downloads/`.
# yt-downloader
