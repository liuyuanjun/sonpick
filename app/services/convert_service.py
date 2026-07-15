import re
import subprocess
from pathlib import Path

from sqlalchemy.orm import Session

from app.models import Song

BITRATE = "320k"


class ConvertService:
    def __init__(self, db: Session):
        self.db = db

    def convert_to_mp3(self, input_path: Path | str, song_id: int | None = None) -> Path:
        input_path = Path(input_path)
        if input_path.suffix.lower() == ".mp3":
            return input_path

        output_dir = input_path.parent / "mp3"
        output_dir.mkdir(exist_ok=True)

        stem = self._normalize(input_path.stem)
        output_path = output_dir / f"{stem}.mp3"
        idx = 1
        while output_path.exists():
            output_path = output_dir / f"{stem} ({idx}).mp3"
            idx += 1

        cmd = [
            "ffmpeg",
            "-y",
            "-i", str(input_path),
            "-map", "0",
            "-c:v", "copy",
            "-ar", "44100",
            "-ac", "2",
            "-b:a", BITRATE,
            "-map_metadata", "0",
            "-id3v2_version", "3",
            str(output_path),
        ]

        result = subprocess.run(cmd, capture_output=True, text=True, timeout=300, errors="replace")
        if result.returncode != 0:
            raise RuntimeError(f"FFmpeg error: {result.stderr[:500]}")

        if song_id:
            song = self.db.get(Song, song_id)
            if song:
                song.local_path = str(output_path)
                song.format = "mp3"
                song.file_size = output_path.stat().st_size if output_path.exists() else song.file_size
                self.db.commit()

        return output_path

    @staticmethod
    def _normalize(text: str) -> str:
        return re.sub(r'[\\/:*?"<>|]', "_", text).strip()
