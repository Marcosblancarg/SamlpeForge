"""
Audio analysis pipeline:
  1. Load audio (librosa, resampled to 48 kHz for CLAP)
  2. Extract CLAP embedding (512-dim)
  3. Extract DSP features via librosa (BPM, key, loudness, spectral centroid)
  4. Store embedding in ChromaDB, features in SQLite catalog
"""
import hashlib
import logging
import time
from pathlib import Path
from typing import Dict, List, Optional

import warnings

import librosa
import numpy as np
from PySide6.QtCore import QObject, QThread, Signal

from config import (
    ANALYSIS_SAMPLE_RATE,
    BATCH_SIZE,
    CLAP_MODEL_ID,
    WORKER_THREADS,
)
from core.catalog import Catalog
from core.vector_store import VectorStore

log = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Lazy model loader — weights download once to ~/.cache/huggingface
# ---------------------------------------------------------------------------
_clap_model = None
_clap_processor = None


def _load_clap():
    global _clap_model, _clap_processor
    if _clap_model is None:
        from transformers import ClapModel, ClapProcessor
        import torch

        log.info("Loading CLAP model %s …", CLAP_MODEL_ID)
        _clap_processor = ClapProcessor.from_pretrained(CLAP_MODEL_ID)
        _clap_model = ClapModel.from_pretrained(CLAP_MODEL_ID)

        # Move to best available device
        if _try_mps():
            _clap_model = _clap_model.to("mps")
            log.info("CLAP running on Apple MPS")
        elif _try_cuda():
            _clap_model = _clap_model.to("cuda")
            log.info("CLAP running on CUDA")
        else:
            log.info("CLAP running on CPU")

        _clap_model.eval()

    return _clap_model, _clap_processor


def _try_mps() -> bool:
    try:
        import torch
        return torch.backends.mps.is_available()
    except Exception:
        return False


def _try_cuda() -> bool:
    try:
        import torch
        return torch.cuda.is_available()
    except Exception:
        return False


# ---------------------------------------------------------------------------
# Per-file analysis
# ---------------------------------------------------------------------------

def _make_embedding_id(file_path: str) -> str:
    return hashlib.sha1(file_path.encode()).hexdigest()


def extract_dsp_features(audio: np.ndarray, sr: int) -> Dict:
    """Extract BPM, key, loudness, and spectral centroid using librosa."""
    features: Dict = {}
    if len(audio) == 0:
        return {"bpm": None, "key_note": None, "loudness_lufs": None, "spectral_centroid": None}

    # BPM
    try:
        tempo, _ = librosa.beat.beat_track(y=audio, sr=sr)
        features["bpm"] = float(tempo)
    except Exception:
        features["bpm"] = None

    # Key (using chroma + Krumhansl-Schmuckler)
    try:
        chroma = librosa.feature.chroma_cqt(y=audio, sr=sr)
        key_idx = int(np.argmax(chroma.mean(axis=1)))
        notes = ["C", "C#", "D", "D#", "E", "F", "F#", "G", "G#", "A", "A#", "B"]
        features["key_note"] = notes[key_idx % 12]
    except Exception:
        features["key_note"] = None

    # Integrated loudness (simple RMS → LUFS approximation)
    try:
        rms = librosa.feature.rms(y=audio)[0].mean()
        lufs = 20 * np.log10(rms + 1e-9) - 0.691
        features["loudness_lufs"] = float(lufs)
    except Exception:
        features["loudness_lufs"] = None

    # Spectral centroid
    try:
        centroid = librosa.feature.spectral_centroid(y=audio, sr=sr)[0].mean()
        features["spectral_centroid"] = float(centroid)
    except Exception:
        features["spectral_centroid"] = None

    return features


MIN_DURATION_SEC = 0.5   # descartar samples menores a 0.5s


def analyse_file(file_path: str, model, processor) -> Optional[Dict]:
    """Full analysis: load audio → DSP → CLAP embedding. Returns feature dict."""
    import torch

    try:
        audio, _ = librosa.load(file_path, sr=ANALYSIS_SAMPLE_RATE, mono=True, duration=30)
    except Exception as exc:
        log.warning("Cannot load %s: %s", file_path, exc)
        return None

    # Descartar archivos demasiado cortos (test files, samples rotos)
    if len(audio) < int(MIN_DURATION_SEC * ANALYSIS_SAMPLE_RATE):
        log.debug("Skipping too-short file (%d samples): %s", len(audio), file_path)
        return None

    # DSP features
    dsp = extract_dsp_features(audio, ANALYSIS_SAMPLE_RATE)

    # CLAP embedding
    try:
        device = next(model.parameters()).device
        inputs = processor(
            audio=audio,                   # 'audios' estaba deprecado → 'audio'
            sampling_rate=ANALYSIS_SAMPLE_RATE,
            return_tensors="pt",
        )
        inputs = {k: v.to(device) for k, v in inputs.items()}
        with torch.no_grad():
            embedding = model.get_audio_features(**inputs)

        # Compatibilidad: versiones nuevas de transformers devuelven
        # BaseModelOutputWithPooling en lugar de un tensor directo
        if hasattr(embedding, "pooler_output"):
            embedding = embedding.pooler_output
        elif hasattr(embedding, "last_hidden_state"):
            embedding = embedding.last_hidden_state[:, 0, :]

        embedding_np = embedding.squeeze().cpu().numpy().tolist()
    except Exception as exc:
        log.warning("CLAP failed for %s: %s", file_path, exc)
        return None

    return {
        "embedding": embedding_np,
        "embedding_id": _make_embedding_id(file_path),
        **dsp,
    }


def get_text_embedding(text: str) -> Optional[List[float]]:
    """Return a 512-dim CLAP text embedding for semantic search."""
    import torch
    try:
        model, processor = _load_clap()
        device = next(model.parameters()).device
        inputs = processor(text=[text], return_tensors="pt")
        inputs = {k: v.to(device) for k, v in inputs.items()}
        with torch.no_grad():
            emb = model.get_text_features(**inputs)

        if hasattr(emb, "pooler_output"):
            emb = emb.pooler_output
        elif hasattr(emb, "last_hidden_state"):
            emb = emb.last_hidden_state[:, 0, :]

        return emb.squeeze().cpu().numpy().tolist()
    except Exception as exc:
        log.error("Text embedding failed: %s", exc)
        return None


# ---------------------------------------------------------------------------
# Worker thread
# ---------------------------------------------------------------------------

class AnalysisWorker(QObject):
    """Analyses pending (unanalysed) samples in the background."""

    progress = Signal(int, int)       # (done, total)
    sample_analysed = Signal(str)     # file_path
    finished = Signal(int)
    error = Signal(str)

    def __init__(self, catalog: Catalog, vector_store: VectorStore):
        super().__init__()
        self.catalog = catalog
        self.vector_store = vector_store
        self._stop = False

    def stop(self):
        self._stop = True

    def run(self):
        try:
            # Load model once
            model, processor = _load_clap()

            all_samples = self.catalog.get_all()
            pending = [s for s in all_samples if s.get("analyzed_at") is None]
            total = len(pending)
            log.info("Analysing %d samples …", total)

            for idx, sample in enumerate(pending):
                if self._stop:
                    break

                fp = sample["file_path"]
                result = analyse_file(fp, model, processor)
                if result:
                    embedding = result.pop("embedding")
                    emb_id = result["embedding_id"]

                    # Store in ChromaDB
                    self.vector_store.upsert(
                        embedding_id=emb_id,
                        embedding=embedding,
                        metadata={"file_path": fp},
                    )

                    # Update SQLite
                    self.catalog.update_analysis(fp, result)
                    self.sample_analysed.emit(fp)

                self.progress.emit(idx + 1, total)

            self.finished.emit(total)

        except Exception as exc:
            log.exception("Analysis worker error")
            self.error.emit(str(exc))
