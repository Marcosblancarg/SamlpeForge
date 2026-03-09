"""
Low-latency audio player using sounddevice.
Emits Qt signals for waveform updates and playback state.
"""
import logging
import threading
import time
from pathlib import Path
from typing import Optional

import numpy as np
import sounddevice as sd
import soundfile as sf
from PySide6.QtCore import QObject, Signal, QTimer

log = logging.getLogger(__name__)


class AudioPlayer(QObject):
    """Thread-safe audio player with position tracking."""

    state_changed = Signal(str)          # "playing" | "paused" | "stopped"
    position_changed = Signal(float)     # position in seconds
    waveform_ready = Signal(object)      # numpy array of peaks
    duration_changed = Signal(float)     # total duration

    def __init__(self, parent=None):
        super().__init__(parent)
        self._audio: Optional[np.ndarray] = None
        self._sr: int = 44100
        self._pos: int = 0               # current frame index
        self._playing = False
        self._stream: Optional[sd.OutputStream] = None
        self._lock = threading.Lock()
        self._volume = 1.0

        # Position timer
        self._timer = QTimer(self)
        self._timer.setInterval(50)      # 50ms update
        self._timer.timeout.connect(self._emit_position)

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------
    def load(self, file_path: str):
        """Load an audio file and prepare for playback."""
        self.stop()
        try:
            data, sr = sf.read(file_path, dtype="float32", always_2d=True)
            # Mix down to mono for display, keep original for playback
            self._audio = data
            self._sr = sr
            self._pos = 0
            self.duration_changed.emit(len(data) / sr)

            # Compute waveform peaks (downsampled)
            from config import MAX_WAVEFORM_SAMPLES
            mono = data.mean(axis=1)
            n_peaks = MAX_WAVEFORM_SAMPLES
            step = max(1, len(mono) // n_peaks)
            peaks = np.array([
                mono[i:i + step].max() for i in range(0, len(mono) - step, step)
            ])
            self.waveform_ready.emit(peaks)
            log.debug("Loaded %s (%.1fs, %dHz)", Path(file_path).name, len(data) / sr, sr)
        except Exception as exc:
            log.error("Player load error: %s", exc)

    def play(self):
        if self._audio is None:
            return
        if self._playing:
            return
        self._playing = True
        self._start_stream()
        self._timer.start()
        self.state_changed.emit("playing")

    def pause(self):
        if not self._playing:
            return
        self._playing = False
        self._stop_stream()
        self._timer.stop()
        self.state_changed.emit("paused")

    def stop(self):
        self._playing = False
        self._stop_stream()
        self._timer.stop()
        self._pos = 0
        self.state_changed.emit("stopped")
        self.position_changed.emit(0.0)

    def seek(self, seconds: float):
        if self._audio is None:
            return
        with self._lock:
            self._pos = int(max(0, min(seconds * self._sr, len(self._audio) - 1)))

    def set_volume(self, volume: float):
        """0.0 – 1.0"""
        self._volume = max(0.0, min(1.0, volume))

    def toggle_play_pause(self):
        if self._playing:
            self.pause()
        else:
            self.play()

    @property
    def duration(self) -> float:
        if self._audio is None:
            return 0.0
        return len(self._audio) / self._sr

    @property
    def position(self) -> float:
        return self._pos / self._sr

    # ------------------------------------------------------------------
    # Internal
    # ------------------------------------------------------------------
    def _start_stream(self):
        self._stop_stream()

        def callback(outdata, frames, time_info, status):
            with self._lock:
                if not self._playing or self._audio is None:
                    outdata[:] = 0
                    return
                end = self._pos + frames
                chunk = self._audio[self._pos:end]
                if len(chunk) == 0:
                    outdata[:] = 0
                    self._playing = False
                    return
                if len(chunk) < frames:
                    # Pad and stop
                    pad = np.zeros((frames - len(chunk), self._audio.shape[1]), dtype=np.float32)
                    chunk = np.vstack([chunk, pad])
                    self._playing = False

                # Adjust channels to match output
                ch = outdata.shape[1]
                if chunk.shape[1] < ch:
                    chunk = np.tile(chunk, (1, ch // chunk.shape[1] + 1))[:, :ch]
                elif chunk.shape[1] > ch:
                    chunk = chunk[:, :ch]

                outdata[:] = chunk * self._volume
                self._pos = min(end, len(self._audio))

        try:
            self._stream = sd.OutputStream(
                samplerate=self._sr,
                channels=min(self._audio.shape[1], 2),
                dtype="float32",
                blocksize=1024,
                callback=callback,
            )
            self._stream.start()
        except Exception as exc:
            log.error("Stream error: %s", exc)
            self._playing = False

    def _stop_stream(self):
        if self._stream:
            try:
                self._stream.stop()
                self._stream.close()
            except Exception:
                pass
            self._stream = None

    def _emit_position(self):
        if self._audio is not None:
            self.position_changed.emit(self._pos / self._sr)
        if not self._playing:
            self._timer.stop()
            self.state_changed.emit("stopped")
