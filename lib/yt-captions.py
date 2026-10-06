# /// script
# requires-python = ">=3.10"
# dependencies = ["yt-dlp[default]"]
# ///

import argparse
import html
import json
from pathlib import Path
import sys
import tempfile

from yt_dlp import YoutubeDL
from yt_dlp.extractor.youtube import YoutubeIE
from yt_dlp.networking import Request
from yt_dlp.networking.exceptions import RequestError
from yt_dlp.utils import DownloadError, ExtractorError


def select_caption(info):
    for source in ("subtitles", "automatic_captions"):
        tracks = info.get(source) or {}
        languages = [
            lang for lang, formats in tracks.items()
            if formats and (lang == "en" or lang.startswith("en-"))
        ]
        preferred = "en" if source == "subtitles" else "en-orig"
        languages.sort(key=lambda lang: (lang != preferred, lang != "en", lang))
        if languages:
            language = languages[0]
            for track in reversed(tracks[language]):
                if track["ext"] == "json3":
                    return source, language, track
            raise ValueError("The English caption track is not available in JSON3 format.")
    raise ValueError("No English captions or automatic English translation are available.")


def caption_text(data):
    lines = []
    for event in data.get("events", []):
        text = "".join(segment.get("utf8", "") for segment in event.get("segs", []))
        text = " ".join(html.unescape(text).split())
        if text:
            lines.append(text)
    if not lines:
        raise ValueError("The English caption track is empty.")
    return "\n".join(lines)


def main():
    parser = argparse.ArgumentParser(
        prog="yt-captions",
        description="Print English YouTube captions, preferring manually added captions."
    )
    parser.add_argument("--refresh", action="store_true", help="Fetch captions again and replace the cached transcript")
    parser.add_argument("--cookies-from-browser", metavar="BROWSER", help="Load cookies from this browser (for example, brave)")
    parser.add_argument("url", help="YouTube video URL")
    args = parser.parse_args()

    try:
        video_id = YoutubeIE.extract_id(args.url)
        cache_dir = Path(tempfile.gettempdir()) / "yt-captions"
        cache_file = cache_dir / f"{video_id}.transcript"
        if not args.refresh:
            try:
                cached = cache_file.read_text(encoding="utf-8")
            except FileNotFoundError:
                pass
            else:
                print(f"yt-captions: using cached transcript ({cache_file})", file=sys.stderr)
                sys.stdout.write(cached)
                return 0

        with YoutubeDL({
            "quiet": True,
            "noplaylist": True,
            # Enables English translations of captions supplied in other languages.
            "writeautomaticsub": True,
            "js_runtimes": {"node": {}},
            "cookiesfrombrowser": (args.cookies_from_browser,) if args.cookies_from_browser else None,
        }) as ydl:
            info = ydl.extract_info(args.url, download=False, process=False)
            if not info or info.get("_type", "video") != "video":
                raise ValueError("Provide a single YouTube video URL.")
            source, language, track = select_caption(info)
            headers = {**info.get("http_headers", {}), **track.get("http_headers", {})}
            with ydl.urlopen(Request(track["url"], headers=headers)) as response:
                text = caption_text(json.load(response))
            cache_dir.mkdir(mode=0o700, parents=True, exist_ok=True)
            # Replace only after writing the complete transcript, including on refresh.
            with tempfile.TemporaryDirectory(dir=cache_dir) as staging:
                staged = Path(staging) / cache_file.name
                staged.write_text(text + "\n", encoding="utf-8")
                staged.replace(cache_file)
            kind = "manual" if source == "subtitles" else "automatic"
            print(f"yt-captions: using {kind} captions ({language})", file=sys.stderr)
            print(text)
    except (DownloadError, ExtractorError, RequestError, ValueError, OSError) as error:
        print(f"yt-captions: {error}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
