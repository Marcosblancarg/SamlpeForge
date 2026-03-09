"""
Main application window — orchestrates all panels and workers.
Layout:
  ┌────────────────────────────────────────────┐
  │  Toolbar: scan btn · search bar · status   │
  ├──────────────────┬──────────────┬──────────┤
  │  Library         │  (waveform   │ Metadata │
  │  Folder Tree +   │   in player  │ + Similar│
  │  Sample Table    │   bar below) │          │
  ├──────────────────┴──────────────┴──────────┤
  │  [Player Bar — always visible]             │
  ├────────────────────────────────────────────┤
  │  Tab: Constellation Map                    │
  └────────────────────────────────────────────┘
"""
import logging
import os
from pathlib import Path
from typing import Dict, List, Optional

from PySide6.QtCore import Qt, QThread, Signal, Slot
from PySide6.QtWidgets import (
    QFileDialog, QHBoxLayout, QLabel, QMainWindow, QProgressBar,
    QPushButton, QSplitter, QStatusBar, QTabWidget, QVBoxLayout, QWidget,
)

from config import APP_NAME
from core.analyzer import AnalysisWorker, get_text_embedding
from core.catalog import Catalog
from core.player import AudioPlayer
from core.scanner import ScanWorker
from core.vector_store import VectorStore
from ui.widgets.constellation import ConstellationMap, build_umap_points
from ui.widgets.drop_box import DropBox
from ui.widgets.library_view import LibraryView
from ui.widgets.metadata_panel import MetadataPanel
from ui.widgets.player_bar import PlayerBar
from ui.widgets.search_bar import SearchBar

log = logging.getLogger(__name__)


class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle(APP_NAME)
        self.resize(1400, 900)

        # Core services
        self.catalog = Catalog()
        self.vector_store = VectorStore()
        self.player = AudioPlayer(self)

        # Worker state
        self._scan_thread: Optional[QThread] = None
        self._scan_worker: Optional[ScanWorker] = None
        self._analysis_thread: Optional[QThread] = None
        self._analysis_worker: Optional[AnalysisWorker] = None

        self._build_ui()
        self._load_stylesheet()
        self._initial_load()

    # ------------------------------------------------------------------
    # UI Construction
    # ------------------------------------------------------------------
    def _build_ui(self):
        central = QWidget()
        self.setCentralWidget(central)
        root_lay = QVBoxLayout(central)
        root_lay.setContentsMargins(8, 8, 8, 4)
        root_lay.setSpacing(6)

        # ── Toolbar ──────────────────────────────────────────────────
        toolbar = QHBoxLayout()
        toolbar.setSpacing(8)

        self.btn_scan = QPushButton("+ Add Folder")
        self.btn_scan.setObjectName("accent")
        self.btn_scan.setFixedWidth(120)
        self.btn_scan.setToolTip("Scan a directory and add samples to catalog")
        self.btn_scan.clicked.connect(self._on_add_folder)

        self.btn_analyse = QPushButton("⚡ Deep Scan")
        self.btn_analyse.setFixedWidth(110)
        self.btn_analyse.setToolTip("Run AI analysis on all pending samples")
        self.btn_analyse.clicked.connect(self._on_start_analysis)

        self.btn_umap = QPushButton("🌌 Build Map")
        self.btn_umap.setFixedWidth(100)
        self.btn_umap.setToolTip("Generate 2D constellation map from embeddings")
        self.btn_umap.clicked.connect(self._on_build_umap)

        self.search_bar = SearchBar()

        self.lbl_count = QLabel("0 samples")
        self.lbl_count.setStyleSheet("color:#555; font-size:12px;")

        toolbar.addWidget(self.btn_scan)
        toolbar.addWidget(self.btn_analyse)
        toolbar.addWidget(self.btn_umap)
        toolbar.addSpacing(8)
        toolbar.addWidget(self.search_bar, 1)
        toolbar.addWidget(self.lbl_count)

        root_lay.addLayout(toolbar)

        # ── Progress bar (hidden by default) ─────────────────────────
        self.progress = QProgressBar()
        self.progress.setVisible(False)
        self.progress.setFixedHeight(4)
        root_lay.addWidget(self.progress)

        # ── Tab widget ────────────────────────────────────────────────
        self.tabs = QTabWidget()
        self.tabs.setTabPosition(QTabWidget.North)

        # Tab 1: Library
        library_tab = self._build_library_tab()
        self.tabs.addTab(library_tab, "Library")

        # Tab 2: Constellation + Drop Zone
        constellation_tab = self._build_constellation_tab()
        self.tabs.addTab(constellation_tab, "Constellation Map")

        root_lay.addWidget(self.tabs, 1)

        # ── Player Bar (always visible) ───────────────────────────────
        self.player_bar = PlayerBar(self.player)
        root_lay.addWidget(self.player_bar)

        # ── Status Bar ────────────────────────────────────────────────
        self.status = QStatusBar()
        self.setStatusBar(self.status)
        self.status.showMessage("Ready")

        # ── Signals ───────────────────────────────────────────────────
        self.search_bar.text_search.connect(self._on_text_search)
        self.search_bar.semantic_search.connect(self._on_semantic_search)
        self.search_bar.filter_changed.connect(self.library.filter_text)

        self.library.sample_selected.connect(self._on_sample_selected)
        self.library.sample_play_requested.connect(self._on_play_sample)
        self.metadata_panel.sample_selected.connect(self._on_play_sample)
        self.metadata_panel.btn_fav.clicked.connect(self._on_toggle_favorite)

    def _build_constellation_tab(self) -> QWidget:
        tab = QWidget()
        lay = QHBoxLayout(tab)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(0)

        splitter = QSplitter(Qt.Horizontal)

        self.constellation = ConstellationMap()
        self.constellation.sample_clicked.connect(self._on_constellation_click)
        splitter.addWidget(self.constellation)

        self.drop_box = DropBox()
        splitter.addWidget(self.drop_box)

        splitter.setStretchFactor(0, 1)
        splitter.setStretchFactor(1, 0)
        splitter.setSizes([900, 200])

        lay.addWidget(splitter)
        return tab

    def _build_library_tab(self) -> QWidget:
        tab = QWidget()
        lay = QHBoxLayout(tab)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(0)

        splitter = QSplitter(Qt.Horizontal)

        self.library = LibraryView()
        splitter.addWidget(self.library)

        self.metadata_panel = MetadataPanel()
        self.metadata_panel.setFixedWidth(280)
        splitter.addWidget(self.metadata_panel)

        splitter.setStretchFactor(0, 1)
        splitter.setStretchFactor(1, 0)

        lay.addWidget(splitter)
        return tab

    def _load_stylesheet(self):
        qss_path = Path(__file__).parent / "styles" / "dark_theme.qss"
        try:
            self.setStyleSheet(qss_path.read_text())
        except Exception as exc:
            log.warning("Could not load stylesheet: %s", exc)

    def _initial_load(self):
        # Limpiar entradas basura de .venv / site-packages si quedaron de scans anteriores
        for bad in (".venv", "site-packages", "dist-packages"):
            removed = self.catalog.purge_paths_containing(bad)
            if removed:
                log.info("Purged %d stale entries containing '%s'", removed, bad)
        samples = self.catalog.get_all()
        self.library.load_samples(samples)
        self._update_count()

    # ------------------------------------------------------------------
    # Scan
    # ------------------------------------------------------------------
    def _on_add_folder(self):
        folder = QFileDialog.getExistingDirectory(self, "Select Audio Library Folder")
        if not folder:
            return

        self._stop_scan()

        worker = ScanWorker(folder, self.catalog)
        thread = QThread(self)
        worker.moveToThread(thread)

        worker.progress.connect(self._on_scan_progress)
        worker.file_scanned.connect(self._on_file_scanned)
        worker.finished.connect(self._on_scan_finished)
        worker.error.connect(lambda e: self.status.showMessage(f"Scan error: {e}"))
        thread.started.connect(worker.run)

        self._scan_worker = worker
        self._scan_thread = thread
        thread.start()

        self.progress.setVisible(True)
        self.btn_scan.setEnabled(False)
        self.status.showMessage(f"Scanning {folder} …")

    @Slot(int, int)
    def _on_scan_progress(self, done: int, total: int):
        if total > 0:
            self.progress.setMaximum(total)
            self.progress.setValue(done)
        self.status.showMessage(f"Scanning… {done}/{total}")

    @Slot(dict)
    def _on_file_scanned(self, meta: Dict):
        self.library.append_samples([meta])
        self._update_count()

    @Slot(int)
    def _on_scan_finished(self, total: int):
        self.progress.setVisible(False)
        self.btn_scan.setEnabled(True)
        self.status.showMessage(f"Scan complete — {total} new files added")
        self._stop_scan()

    def _stop_scan(self):
        if self._scan_worker:
            self._scan_worker.stop()
        if self._scan_thread:
            self._scan_thread.quit()
            self._scan_thread.wait(2000)
        self._scan_worker = None
        self._scan_thread = None

    # ------------------------------------------------------------------
    # Analysis
    # ------------------------------------------------------------------
    def _on_start_analysis(self):
        pending = self.catalog.count() - self.catalog.count_analyzed()
        if pending == 0:
            self.status.showMessage("All samples already analysed.")
            return

        self._stop_analysis()

        worker = AnalysisWorker(self.catalog, self.vector_store)
        thread = QThread(self)
        worker.moveToThread(thread)

        worker.progress.connect(self._on_analysis_progress)
        worker.sample_analysed.connect(self._on_sample_analysed)
        worker.finished.connect(self._on_analysis_finished)
        worker.error.connect(lambda e: self.status.showMessage(f"Analysis error: {e}"))
        thread.started.connect(worker.run)

        self._analysis_worker = worker
        self._analysis_thread = thread
        thread.start()

        self.progress.setVisible(True)
        self.btn_analyse.setEnabled(False)
        self.status.showMessage(f"Analysing {pending} samples…")

    @Slot(int, int)
    def _on_analysis_progress(self, done: int, total: int):
        if total > 0:
            self.progress.setMaximum(total)
            self.progress.setValue(done)
        self.status.showMessage(f"Analysing… {done}/{total}")

    @Slot(str)
    def _on_sample_analysed(self, file_path: str):
        # Refresh currently selected sample if it was just analysed
        sel = self.library.selected_row()
        if sel and sel.get("file_path") == file_path:
            updated = self.catalog.get_by_path(file_path)
            if updated:
                self.metadata_panel.load_sample(updated)

    @Slot(int)
    def _on_analysis_finished(self, total: int):
        self.progress.setVisible(False)
        self.btn_analyse.setEnabled(True)
        self.status.showMessage(f"Analysis complete — {total} samples processed")
        # Reload library to show updated features
        self.library.load_samples(self.catalog.get_all())
        self._stop_analysis()

    def _stop_analysis(self):
        if self._analysis_worker:
            self._analysis_worker.stop()
        if self._analysis_thread:
            self._analysis_thread.quit()
            self._analysis_thread.wait(3000)
        self._analysis_worker = None
        self._analysis_thread = None

    # ------------------------------------------------------------------
    # UMAP Constellation
    # ------------------------------------------------------------------
    def _on_build_umap(self):
        self.status.showMessage("Building UMAP projection…")
        self.btn_umap.setEnabled(False)
        try:
            data = self.vector_store.get_all_embeddings()
            ids = data.get("ids", [])
            embeddings = data.get("embeddings", [])
            metadatas = data.get("metadatas", [])

            if len(embeddings) < 5:
                self.status.showMessage("Need at least 5 analysed samples for the map.")
                self.btn_umap.setEnabled(True)
                return

            # Enrich metadatas with catalog info (category)
            enriched = []
            for meta in metadatas:
                fp = meta.get("file_path", "")
                row = self.catalog.get_by_path(fp) or {}
                enriched.append({**meta, "category": row.get("category", "")})

            points = build_umap_points(embeddings, enriched)
            self.constellation.load_points(points)
            self.tabs.setCurrentIndex(1)
            self.status.showMessage(f"Constellation map built — {len(points)} samples")
        except Exception as exc:
            log.exception("UMAP error")
            self.status.showMessage(f"Map error: {exc}")
        finally:
            self.btn_umap.setEnabled(True)

    # ------------------------------------------------------------------
    # Sample Selection & Playback
    # ------------------------------------------------------------------
    @Slot(dict)
    def _on_sample_selected(self, meta: Dict):
        self.metadata_panel.load_sample(meta)
        # Find similar samples if embedding exists
        if meta.get("embedding_id"):
            try:
                emb_data = self.vector_store._col.get(
                    ids=[meta["embedding_id"]], include=["embeddings"]
                )
                embs = emb_data.get("embeddings", [])
                if embs:
                    similar_ids = self.vector_store.find_similar(embs[0])
                    # Remove self
                    similar_ids = [s for s in similar_ids if s["id"] != meta["embedding_id"]]
                    # Enrich with catalog data
                    fps = [s["file_path"] for s in similar_ids]
                    rows = {r["file_path"]: r for r in self.catalog.get_all() if r["file_path"] in fps}
                    enriched = []
                    for s in similar_ids:
                        row = rows.get(s["file_path"], {})
                        enriched.append({**row, "distance": s["distance"]})
                    self.metadata_panel.set_similar(enriched)
            except Exception as exc:
                log.debug("Similar search error: %s", exc)

    @Slot(str)
    def _on_play_sample(self, file_path: str):
        meta = self.catalog.get_by_path(file_path) or {}
        self.player_bar.load_sample(file_path, meta.get("file_name", ""))

    @Slot(str)
    def _on_constellation_click(self, file_path: str):
        meta = self.catalog.get_by_path(file_path)
        if meta:
            self.metadata_panel.load_sample(meta)
            self._on_play_sample(file_path)

    def _on_toggle_favorite(self):
        sel = self.library.selected_row()
        if sel:
            current = bool(sel.get("favorite"))
            self.catalog.set_favorite(sel["file_path"], not current)
            updated = self.catalog.get_by_path(sel["file_path"])
            if updated:
                self.metadata_panel.load_sample(updated)

    # ------------------------------------------------------------------
    # Search
    # ------------------------------------------------------------------
    @Slot(str)
    def _on_text_search(self, query: str):
        results = self.catalog.search(query)
        self.library.load_samples(results)
        self.search_bar.set_status(f"{len(results)} results")
        self.status.showMessage(f"Search: '{query}' → {len(results)} samples")

    @Slot(str)
    def _on_semantic_search(self, query: str):
        self.status.showMessage(f"Running semantic search: '{query}'…")
        embedding = get_text_embedding(query)
        if not embedding:
            self.status.showMessage("Failed to generate text embedding.")
            self.search_bar.set_status("Error")
            return

        similar = self.vector_store.find_by_text(embedding)
        if not similar:
            self.status.showMessage("No results found.")
            self.search_bar.set_status("0 results")
            return

        fps = [s["file_path"] for s in similar]
        rows = {r["file_path"]: r for r in self.catalog.get_all() if r["file_path"] in fps}
        results = []
        for s in similar:
            row = rows.get(s["file_path"])
            if row:
                results.append(row)

        self.library.load_samples(results)
        msg = f"{len(results)} semantic matches for: \"{query}\""
        self.search_bar.set_status(f"{len(results)} results")
        self.status.showMessage(msg)

    # ------------------------------------------------------------------
    def _update_count(self):
        n = self.catalog.count()
        na = self.catalog.count_analyzed()
        self.lbl_count.setText(f"{n:,} samples · {na:,} analysed")

    # ------------------------------------------------------------------
    def closeEvent(self, event):
        self._stop_scan()
        self._stop_analysis()
        self.player.stop()
        event.accept()
