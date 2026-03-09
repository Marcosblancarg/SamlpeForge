"""Right-side metadata panel + similar samples list."""
import logging
from typing import Dict, List, Optional

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QFrame, QHBoxLayout, QLabel, QListWidget, QListWidgetItem,
    QPushButton, QScrollArea, QSizePolicy, QVBoxLayout, QWidget,
)

log = logging.getLogger(__name__)

_STAR = "★"
_STAR_EMPTY = "☆"


class MetaRow(QWidget):
    """Label + value pair."""
    def __init__(self, label: str, value: str, parent=None):
        super().__init__(parent)
        lay = QHBoxLayout(self)
        lay.setContentsMargins(0, 2, 0, 2)
        lay.setSpacing(8)

        lbl = QLabel(label)
        lbl.setObjectName("title")
        lbl.setFixedWidth(100)
        lbl.setAlignment(Qt.AlignRight | Qt.AlignVCenter)

        val = QLabel(value)
        val.setObjectName("value")
        val.setWordWrap(True)

        lay.addWidget(lbl)
        lay.addWidget(val, 1)
        self.val_label = val

    def set_value(self, v: str):
        self.val_label.setText(v)


class MetadataPanel(QWidget):
    """Displays metadata for the selected sample and a similar-samples list."""

    sample_selected = Signal(str)        # file_path double-clicked in similar list

    def __init__(self, parent=None):
        super().__init__(parent)
        self._build_ui()

    def _build_ui(self):
        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        # ── Metadata section ────────────────────────────────────────
        meta_frame = QFrame()
        meta_frame.setObjectName("panel")
        meta_lay = QVBoxLayout(meta_frame)
        meta_lay.setContentsMargins(12, 12, 12, 12)
        meta_lay.setSpacing(2)

        header = QHBoxLayout()
        title = QLabel("METADATA")
        title.setObjectName("title")
        self.btn_fav = QPushButton(_STAR_EMPTY)
        self.btn_fav.setObjectName("icon_btn")
        self.btn_fav.setFixedSize(28, 28)
        self.btn_fav.setToolTip("Toggle Favorite")
        header.addWidget(title)
        header.addStretch()
        header.addWidget(self.btn_fav)
        meta_lay.addLayout(header)

        self.row_name      = MetaRow("File",       "—")
        self.row_format    = MetaRow("Format",     "—")
        self.row_duration  = MetaRow("Duration",   "—")
        self.row_sr        = MetaRow("Sample Rate","—")
        self.row_bit       = MetaRow("Bit Depth",  "—")
        self.row_channels  = MetaRow("Channels",   "—")
        self.row_bpm       = MetaRow("BPM",        "—")
        self.row_key       = MetaRow("Key",        "—")
        self.row_loudness  = MetaRow("Loudness",   "—")
        self.row_centroid  = MetaRow("Centroid",   "—")
        self.row_category  = MetaRow("Category",  "—")
        self.row_tags      = MetaRow("Tags",       "—")

        for row in (
            self.row_name, self.row_format, self.row_duration, self.row_sr,
            self.row_bit, self.row_channels, self.row_bpm, self.row_key,
            self.row_loudness, self.row_centroid, self.row_category, self.row_tags,
        ):
            meta_lay.addWidget(row)

        root.addWidget(meta_frame)

        # ── Similar Samples ──────────────────────────────────────────
        sim_frame = QFrame()
        sim_frame.setObjectName("panel")
        sim_lay = QVBoxLayout(sim_frame)
        sim_lay.setContentsMargins(12, 12, 12, 12)
        sim_lay.setSpacing(6)

        sim_title = QLabel("SIMILAR SAMPLES")
        sim_title.setObjectName("title")
        sim_lay.addWidget(sim_title)

        self.similar_list = QListWidget()
        self.similar_list.setAlternatingRowColors(True)
        self.similar_list.itemDoubleClicked.connect(self._on_similar_dclick)
        sim_lay.addWidget(self.similar_list)

        root.addWidget(sim_frame, 1)

    # ------------------------------------------------------------------
    def load_sample(self, meta: Dict):
        def _v(key, fmt=None, unit=""):
            val = meta.get(key)
            if val is None:
                return "—"
            if fmt:
                try:
                    return f"{fmt.format(val)}{unit}"
                except Exception:
                    return str(val)
            return str(val) + unit

        dur = meta.get("duration_sec")
        dur_str = f"{int(dur // 60):02d}:{int(dur % 60):02d}" if dur else "—"

        self.row_name.set_value(meta.get("file_name", "—"))
        self.row_format.set_value(meta.get("extension", "—").upper().lstrip("."))
        self.row_duration.set_value(dur_str)
        self.row_sr.set_value(_v("sample_rate", unit=" Hz"))
        self.row_bit.set_value(_v("bit_depth", unit=" bit"))
        self.row_channels.set_value(_v("channels"))
        self.row_bpm.set_value(_v("bpm", "{:.1f}"))
        self.row_key.set_value(_v("key_note"))
        self.row_loudness.set_value(_v("loudness_lufs", "{:.1f}", " LUFS"))
        self.row_centroid.set_value(_v("spectral_centroid", "{:.0f}", " Hz"))
        self.row_category.set_value(_v("category"))

        tags = meta.get("tags") or []
        self.row_tags.set_value(", ".join(tags) if tags else "—")

        fav = bool(meta.get("favorite"))
        self.btn_fav.setText(_STAR if fav else _STAR_EMPTY)

    def set_similar(self, samples: List[Dict]):
        self.similar_list.clear()
        for s in samples:
            name = s.get("file_name", s.get("file_path", ""))
            dist = s.get("distance", 0.0)
            pct = max(0, int((1 - dist) * 100))
            item = QListWidgetItem(f"{name}  [{pct}%]")
            item.setData(Qt.UserRole, s.get("file_path", ""))
            item.setToolTip(s.get("file_path", ""))
            self.similar_list.addItem(item)

    def _on_similar_dclick(self, item: QListWidgetItem):
        fp = item.data(Qt.UserRole)
        if fp:
            self.sample_selected.emit(fp)
