#!/usr/bin/env python3
# wmmn / 我密码呢
"""Download audio/video with yt-dlp."""
import argparse
import json
import sys
from pathlib import Path


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--url", required=True)
    ap.add_argument("--out", required=True)
    ap.add_argument("--audio-only", action="store_true")
    ap.add_argument("--no-playlist", action="store_true")
    args = ap.parse_args()
    try:
        import yt_dlp
    except ImportError:
        print("Missing yt-dlp. Run: pip install -r requirements-optional.txt", file=sys.stderr)
        return 1
    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    template = "001.%(ext)s" if args.no_playlist else "%(playlist_index)03d_%(title).80s.%(ext)s"
    opts = {
        "outtmpl": str(out / template),
        "noplaylist": args.no_playlist,
        "quiet": False,
        "no_warnings": True,
        "retries": 3,
        "fragment_retries": 3,
        "socket_timeout": 30,
    }
    if args.audio_only:
        opts["format"] = "bestaudio[ext=m4a]/bestaudio"
    else:
        opts["format"] = "bv*+ba/b"
    with yt_dlp.YoutubeDL(opts) as ydl:
        ydl.download([args.url])
    media_suffixes = {".mp4", ".mkv", ".webm", ".mov", ".m4v", ".avi", ".flv", ".mp3", ".m4a", ".wav", ".aac", ".flac"}
    files = sorted(
        path.name
        for path in out.iterdir()
        if path.is_file() and path.suffix.lower() in media_suffixes
    )
    manifest = {"schema_version": "1.0", "source": args.url, "files": files}
    (out / "download_manifest.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps({"out": str(out), "files": files}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())



