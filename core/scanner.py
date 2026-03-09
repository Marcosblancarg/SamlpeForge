"""Multi-threaded directory scanner with Qt signals for UI feedback."""
import logging
import os
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from typing import List, Optional

import soundfile as sf
from mutagen import File as MutagenFile
from PySide6.QtCore import QObject, QThread, Signal

from config import SUPPORTED_EXTENSIONS, WORKER_THREADS
from core.catalog import Catalog

log = logging.getLogger(__name__)


def _probe_file(file_path: str) -> Optional[dict]:
    """Extract lightweight metadata from a file without full analysis."""
    path = Path(file_path)
    try:
        stat = path.stat()
        meta = {
            "file_path": file_path,
            "file_name": path.name,
            "extension": path.suffix.lower(),
            "size_bytes": stat.st_size,
        }

        # Try soundfile first (accurate for PCM formats)
        try:
            info = sf.info(file_path)
            meta["sample_rate"] = info.samplerate
            meta["channels"] = info.channels
            meta["duration_sec"] = info.frames / info.samplerate
            meta["bit_depth"] = {"PCM_16": 16, "PCM_24": 24, "PCM_32": 32, "FLOAT": 32}.get(
                info.subtype, 0
            )
        except Exception:
            # Fallback: mutagen for compressed formats
            mf = MutagenFile(file_path)
            if mf and hasattr(mf, "info"):
                meta["sample_rate"] = getattr(mf.info, "sample_rate", 0)
                meta["channels"] = getattr(mf.info, "channels", 0)
                meta["duration_sec"] = getattr(mf.info, "length", 0.0)
                meta["bit_depth"] = getattr(mf.info, "bits_per_sample", 0)

        return meta
    except Exception as exc:
        log.debug("Skipping %s: %s", file_path, exc)
        return None


# Carpetas a ignorar siempre (entornos virtuales, caches, sistema)
_SKIP_DIRS = {
    ".venv", "venv", "env", ".env",
    "site-packages", "dist-packages",
    "__pycache__", ".git", ".DS_Store",
    "node_modules", ".tox", ".mypy_cache",
}


def _should_skip(dirpath: str) -> bool:
    """True si algún componente de la ruta está en la lista negra."""
    parts = Path(dirpath).parts
    return any(p in _SKIP_DIRS or p.startswith(".") for p in parts)


def _collect_audio_files(root: str) -> List[str]:
    """Recursively collect all audio file paths under root, skipping system dirs."""
    collected = []
    for dirpath, dirs, files in os.walk(root):
        # Poda en-place: evita bajar a carpetas ignoradas
        dirs[:] = [
            d for d in dirs
            if d not in _SKIP_DIRS and not d.startswith(".")
        ]
        if _should_skip(dirpath):
            continue
        for f in files:
            if Path(f).suffix.lower() in SUPPORTED_EXTENSIONS:
                collected.append(os.path.join(dirpath, f))
    return collected


class ScanWorker(QObject):
    """Runs in a QThread. Emits progress signals to the UI."""

    progress = Signal(int, int)       # (current, total)
    file_scanned = Signal(dict)       # metadata dict for each file
    finished = Signal(int)            # total files scanned
    error = Signal(str)

    def __init__(self, root_dir: str, catalog: Catalog):
        super().__init__()
        self.root_dir = root_dir
        self.catalog = catalog
        self._stop = False

    def stop(self):
        self._stop = True

    def run(self):
        try:
            log.info("Collecting files under %s …", self.root_dir)
            all_files = _collect_audio_files(self.root_dir)
            total = len(all_files)
            log.info("Found %d audio files", total)

            # Filter already-scanned files
            pending = [f for f in all_files if not self.catalog.exists(f)]
            log.info("%d new files to scan", len(pending))

            scanned = 0
            with ThreadPoolExecutor(max_workers=WORKER_THREADS) as executor:
                futures = {executor.submit(_probe_file, fp): fp for fp in pending}
                for future in as_completed(futures):
                    if self._stop:
                        executor.shutdown(wait=False, cancel_futures=True)
                        break
                    result = future.result()
                    if result:
                        self.catalog.upsert_sample(result)
                        self.file_scanned.emit(result)
                    scanned += 1
                    self.progress.emit(scanned, len(pending))

            self.finished.emit(scanned)
        except Exception as exc:
            log.exception("Scanner error")
            self.error.emit(str(exc))
