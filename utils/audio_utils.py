"""Audio utility helpers."""
from pathlib import Path
from typing import Optional

from config import SUPPORTED_EXTENSIONS


def is_audio_file(path: str) -> bool:
    return Path(path).suffix.lower() in SUPPORTED_EXTENSIONS


def format_duration(seconds: Optional[float]) -> str:
    if seconds is None:
        return "—"
    s = int(seconds)
    m, s = divmod(s, 60)
    if m >= 60:
        h, m = divmod(m, 60)
        return f"{h}:{m:02d}:{s:02d}"
    return f"{m:02d}:{s:02d}"


def format_size(bytes_: Optional[int]) -> str:
    if bytes_ is None:
        return "—"
    for unit in ("B", "KB", "MB", "GB"):
        if bytes_ < 1024:
            return f"{bytes_:.1f} {unit}"
        bytes_ /= 1024
    return f"{bytes_:.1f} TB"


def guess_category(file_name: str) -> Optional[str]:
    """Heuristic category from filename keywords."""
    name = file_name.lower()
    mapping = {
        "kick":       "Kick",
        "bd ":        "Kick",
        "bass drum":  "Kick",
        "snare":      "Snare",
        "snr":        "Snare",
        "clap":       "Snare",
        "hihat":      "Hi-Hat",
        "hi-hat":     "Hi-Hat",
        "hh ":        "Hi-Hat",
        "open hat":   "Hi-Hat",
        "closed hat": "Hi-Hat",
        "cymbal":     "Cymbal",
        "crash":      "Cymbal",
        "ride":       "Cymbal",
        "bass":       "Bass",
        "sub":        "Bass",
        "808":        "Bass",
        "lead":       "Lead",
        "synth":      "Lead",
        "pad":        "Pad",
        "atmosphere": "Pad",
        "vocal":      "Vocal",
        "vox":        "Vocal",
        "acapella":   "Vocal",
        "fx":         "FX",
        "riser":      "FX",
        "sweep":      "FX",
        "loop":       "Loop",
        "perc":       "Percussion",
        "shaker":     "Percussion",
        "tambourine": "Percussion",
    }
    for keyword, category in mapping.items():
        if keyword in name:
            return category
    return None
