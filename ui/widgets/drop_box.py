"""
Quick Drop Zone — panel lateral que acepta archivos de audio arrastrados desde
el Constellation Map o la Library, y permite arrastrarlos a un DAW.
"""
from pathlib import Path

from PySide6.QtCore import Qt, QMimeData, QUrl
from PySide6.QtGui import QDrag
from PySide6.QtWidgets import (
    QAbstractItemView, QFrame, QHBoxLayout, QLabel,
    QListWidget, QPushButton, QVBoxLayout, QWidget,
)


class _FileList(QListWidget):
    """Lista interna que emite archivos como URI MIME al arrastrar."""

    def __init__(self):
        super().__init__()
        self._paths: list[str] = []
        self.setDragEnabled(True)
        self.setSelectionMode(QAbstractItemView.ExtendedSelection)
        self.setDragDropMode(QAbstractItemView.DragOnly)
        self.setAlternatingRowColors(True)
        self.setSpacing(1)

    def add_file(self, file_path: str) -> bool:
        """Agrega el archivo; retorna False si ya existía."""
        if file_path in self._paths:
            return False
        self._paths.append(file_path)
        self.addItem(Path(file_path).name)
        return True

    def clear(self):
        super().clear()
        self._paths.clear()

    def startDrag(self, supported_actions):
        selected = self.selectedIndexes()
        if not selected:
            return
        paths = [self._paths[i.row()] for i in selected if i.row() < len(self._paths)]
        if not paths:
            return
        mime = QMimeData()
        mime.setUrls([QUrl.fromLocalFile(p) for p in paths])
        drag = QDrag(self)
        drag.setMimeData(mime)
        drag.exec(Qt.CopyAction)


class DropBox(QFrame):
    """
    Cuadro de drop rápido para el costado derecho del Constellation Map.
    - Acepta drops de archivos de audio desde el mapa o la library.
    - Muestra la lista de samples acumulados.
    - Permite arrastrar ítems de la lista directamente a un DAW.
    """

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setAcceptDrops(True)
        self.setFrameShape(QFrame.StyledPanel)
        self.setObjectName("DropBox")
        self.setMinimumWidth(160)
        self.setMaximumWidth(260)
        self._build_ui()

    def _build_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(8, 10, 8, 8)
        layout.setSpacing(6)

        title = QLabel("Drop Zone")
        title.setObjectName("DropBoxTitle")
        title.setStyleSheet("font-weight: bold; font-size: 13px; color: #9ca3af;")

        self._hint = QLabel("Arrastra samples\ndesde el mapa aquí")
        self._hint.setAlignment(Qt.AlignCenter)
        self._hint.setStyleSheet(
            "color: #4b5563; font-size: 11px; padding: 20px 0;"
        )

        self._list = _FileList()

        bottom = QHBoxLayout()
        self._lbl_count = QLabel("0 archivos")
        self._lbl_count.setStyleSheet("color: #6b7280; font-size: 11px;")
        btn_clear = QPushButton("Limpiar")
        btn_clear.setFixedWidth(60)
        btn_clear.clicked.connect(self._on_clear)
        bottom.addWidget(self._lbl_count)
        bottom.addStretch()
        bottom.addWidget(btn_clear)

        layout.addWidget(title)
        layout.addWidget(self._hint)
        layout.addWidget(self._list, 1)
        layout.addLayout(bottom)

    # ------------------------------------------------------------------
    def dragEnterEvent(self, event):
        if event.mimeData().hasUrls():
            self.setProperty("dragOver", True)
            self.setStyleSheet(
                "QFrame#DropBox { border: 1px solid #6366f1; border-radius: 6px; }"
            )
            event.acceptProposedAction()

    def dragLeaveEvent(self, event):
        self._reset_style()

    def dropEvent(self, event):
        self._reset_style()
        added = 0
        for url in event.mimeData().urls():
            fp = url.toLocalFile()
            if fp:
                if self._list.add_file(fp):
                    added += 1
        if added:
            self._update_count()
        event.acceptProposedAction()

    def _on_clear(self):
        self._list.clear()
        self._update_count()

    def _update_count(self):
        n = self._list.count()
        self._lbl_count.setText(f"{n} archivo{'s' if n != 1 else ''}")
        self._hint.setVisible(n == 0)

    def _reset_style(self):
        self.setStyleSheet("")
