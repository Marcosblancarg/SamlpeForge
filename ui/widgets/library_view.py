"""
Library panel: folder tree (left) + sample table (right).
Supports drag-and-drop to DAW and double-click to play.
"""
import logging
import os
from pathlib import Path
from typing import Dict, List, Optional

from PySide6.QtCore import (
    QAbstractTableModel, QMimeData, QModelIndex, QSortFilterProxyModel,
    Qt, Signal, QUrl,
)
from PySide6.QtGui import QColor, QDrag
from PySide6.QtWidgets import (
    QAbstractItemView, QFileSystemModel, QFrame, QHBoxLayout,
    QHeaderView, QSplitter, QTableView, QTreeView, QVBoxLayout, QWidget,
)

log = logging.getLogger(__name__)

COLUMNS = ["Name", "Format", "Duration", "BPM", "Key", "SR", "Loudness", "Category", "Tags"]
COL_IDX = {c: i for i, c in enumerate(COLUMNS)}


class SampleTableModel(QAbstractTableModel):
    def __init__(self, parent=None):
        super().__init__(parent)
        self._data: List[Dict] = []

    def load(self, rows: List[Dict]):
        self.beginResetModel()
        self._data = rows
        self.endResetModel()

    def append_rows(self, rows: List[Dict]):
        if not rows:
            return
        first = len(self._data)
        self.beginInsertRows(QModelIndex(), first, first + len(rows) - 1)
        self._data.extend(rows)
        self.endInsertRows()

    def rowCount(self, parent=QModelIndex()):
        return len(self._data)

    def columnCount(self, parent=QModelIndex()):
        return len(COLUMNS)

    def headerData(self, section, orientation, role=Qt.DisplayRole):
        if role == Qt.DisplayRole and orientation == Qt.Horizontal:
            return COLUMNS[section]

    def data(self, index: QModelIndex, role=Qt.DisplayRole):
        if not index.isValid():
            return None
        row = self._data[index.row()]
        col = COLUMNS[index.column()]

        if role == Qt.DisplayRole:
            return self._format_cell(row, col)
        if role == Qt.UserRole:
            return row.get("file_path", "")
        if role == Qt.ForegroundRole:
            if row.get("analyzed_at") is None:
                return QColor("#555555")
        if role == Qt.ToolTipRole:
            return row.get("file_path", "")
        return None

    def get_row(self, index: int) -> Optional[Dict]:
        if 0 <= index < len(self._data):
            return self._data[index]
        return None

    def _format_cell(self, row: Dict, col: str) -> str:
        if col == "Name":
            return row.get("file_name", "")
        if col == "Format":
            return row.get("extension", "").lstrip(".").upper()
        if col == "Duration":
            dur = row.get("duration_sec")
            if dur:
                return f"{int(dur//60):02d}:{int(dur%60):02d}"
            return "—"
        if col == "BPM":
            v = row.get("bpm")
            return f"{v:.1f}" if v else "—"
        if col == "Key":
            return row.get("key_note") or "—"
        if col == "SR":
            v = row.get("sample_rate")
            return f"{v//1000}k" if v else "—"
        if col == "Loudness":
            v = row.get("loudness_lufs")
            return f"{v:.1f}" if v else "—"
        if col == "Category":
            return row.get("category") or "—"
        if col == "Tags":
            tags = row.get("tags") or []
            return ", ".join(tags[:3]) if tags else "—"
        return ""

    # --- Drag & Drop (file drag to DAW) ---
    def flags(self, index):
        base = super().flags(index)
        return base | Qt.ItemIsDragEnabled

    def mimeTypes(self):
        return ["text/uri-list"]

    def mimeData(self, indexes):
        paths = list({self._data[i.row()].get("file_path", "") for i in indexes if i.column() == 0})
        mime = QMimeData()
        mime.setUrls([QUrl.fromLocalFile(p) for p in paths if p])
        return mime


class LibraryView(QWidget):
    """Folder browser + sample list with signals for selection and play."""

    sample_selected = Signal(dict)       # full metadata row
    sample_play_requested = Signal(str)  # file_path

    def __init__(self, parent=None):
        super().__init__(parent)
        self._build_ui()

    def _build_ui(self):
        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        splitter = QSplitter(Qt.Horizontal)

        # ── Folder Tree ──────────────────────────────────────────────
        self._fs_model = QFileSystemModel()
        self._fs_model.setRootPath("")
        self._fs_model.setNameFilters(["*"])
        self._fs_model.setNameFilterDisables(False)

        self.folder_tree = QTreeView()
        self.folder_tree.setModel(self._fs_model)
        self.folder_tree.setRootIndex(self._fs_model.index(str(Path.home())))
        self.folder_tree.setMinimumWidth(180)
        self.folder_tree.setMaximumWidth(280)
        # Hide size, type, date columns
        for col in (1, 2, 3):
            self.folder_tree.hideColumn(col)
        self.folder_tree.setHeaderHidden(True)
        self.folder_tree.clicked.connect(self._on_folder_clicked)

        # ── Sample Table ─────────────────────────────────────────────
        self._model = SampleTableModel()
        self._proxy = QSortFilterProxyModel()
        self._proxy.setSourceModel(self._model)
        self._proxy.setFilterCaseSensitivity(Qt.CaseInsensitive)
        self._proxy.setFilterKeyColumn(-1)

        self.table = QTableView()
        self.table.setModel(self._proxy)
        self.table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.table.setSelectionMode(QAbstractItemView.ExtendedSelection)
        self.table.setAlternatingRowColors(True)
        self.table.setSortingEnabled(True)
        self.table.setShowGrid(False)
        self.table.verticalHeader().setVisible(False)
        self.table.verticalHeader().setDefaultSectionSize(24)
        self.table.horizontalHeader().setStretchLastSection(True)

        # Column widths
        widths = [200, 60, 60, 60, 50, 50, 70, 100, 150]
        for i, w in enumerate(widths):
            self.table.setColumnWidth(i, w)

        # Drag from table
        self.table.setDragEnabled(True)
        self.table.setDragDropMode(QAbstractItemView.DragOnly)
        self.table.setDefaultDropAction(Qt.CopyAction)

        self.table.selectionModel().selectionChanged.connect(self._on_selection_changed)
        self.table.doubleClicked.connect(self._on_double_click)

        splitter.addWidget(self.folder_tree)
        splitter.addWidget(self.table)
        splitter.setStretchFactor(0, 0)
        splitter.setStretchFactor(1, 1)

        layout.addWidget(splitter)

    # ------------------------------------------------------------------
    def load_samples(self, samples: List[Dict]):
        self._model.load(samples)

    def append_samples(self, samples: List[Dict]):
        self._model.append_rows(samples)

    def filter_text(self, text: str):
        self._proxy.setFilterFixedString(text)

    def selected_row(self) -> Optional[Dict]:
        idxs = self.table.selectionModel().selectedRows()
        if not idxs:
            return None
        src = self._proxy.mapToSource(idxs[0])
        return self._model.get_row(src.row())

    # ------------------------------------------------------------------
    def _on_folder_clicked(self, index):
        path = self._fs_model.filePath(index)
        # Emit to parent to trigger folder-scoped filter
        # (handled by MainWindow by calling filter_folder)
        self.filter_folder(path)

    def filter_folder(self, folder_path: str):
        """Show only samples inside folder_path."""
        self._proxy.setFilterRole(Qt.UserRole)
        # Custom: filter by file_path prefix
        self._proxy.setFilterFixedString("")
        # Use a regex on the full path (UserRole)
        import re
        escaped = re.escape(folder_path)
        self._proxy.setFilterRegularExpression(escaped)
        self._proxy.setFilterRole(Qt.ToolTipRole)

    def _on_selection_changed(self):
        row = self.selected_row()
        if row:
            self.sample_selected.emit(row)

    def _on_double_click(self, proxy_idx):
        src = self._proxy.mapToSource(proxy_idx)
        row = self._model.get_row(src.row())
        if row:
            self.sample_play_requested.emit(row["file_path"])
