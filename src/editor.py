import os, json, time, bisect, traceback
from typing import List, Optional, Dict

from PySide6 import QtWidgets, QtGui, QtCore
from PySide6.QtGui import QShortcut
from PySide6.QtCore import Qt, QTimer
from render_settings import RenderSettingsDialog
from effects import EffectConfig, build_chain
# Verfügbare Effekte für das UI (key -> Anzeigename)
AVAILABLE_EFFECTS = {
    "bw": "Black & White",
    "invert": "Invert Colors",
    "sepia": "Sepia Tone",
    "brightness": "Brightness",
    "contrast": "Contrast",
    "mirror": "Mirror (Horizontal Flip)",
}

REVERSE_AVAILABLE_EFFECTS = {v: k for k, v in AVAILABLE_EFFECTS.items()}
import vlc
from moviepy import (
    VideoFileClip, AudioFileClip, ColorClip,
    concatenate_videoclips, CompositeAudioClip
)

# Aus deinen Modulen
from models import ClipItem, AudioItem
from timeline import TimelineScene, TimelineView
from preview import FramePreviewer
from utils import (
    fmt_time, make_subclip, make_audio_subclip,
    set_start_compat, set_audio_compat
)


class EditorMainWindow(QtWidgets.QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Simpledit – Timeline Editor")
        self.resize(1440, 880)

        # State
        self.pps = 80.0
        self.clips: List[ClipItem] = []
        self.audios: List[AudioItem] = []
        self.graphics_by_clip: dict[int, object] = {}
        self.audio_graphics_by_clip: dict[int, object] = {}
        self.project_path: Optional[str] = None
        self.current_time: float = 0.0
        self.playing = False
        self.audio_enabled = True
        self.preview_height = 360   # Preview-Höhe
        self.preview_fps = 30
        self.render_settings = {
            "resolution": "Auto",
            "fps": "Auto",
            "codec": "libx264 (H.264)",
            "preset": "medium",
            "audio_bitrate": "192k",
        }

        # ---------- Playback/Sync State ----------
        # Welche Pfade sind aktuell aktiv? (wird für Set-Vergleich genutzt)
        self._active_paths: set[str] = set()
        # Letzte "gesetzte" Zeit pro Pfad (ms), um unnötige Seeks zu vermeiden
        self._last_seek_by_path: Dict[str, int] = {}
        # Rate-Limit per Pfad (Wallclock ms)
        self._last_seek_wall_ms: Dict[str, int] = {}
        # Schwellwerte für Sync-Ruhe
        self._seek_guard_ms = 350    # erst seeken, wenn Delta größer als das ist
        self._seek_min_interval_ms = 1200  # min. Zeit zwischen zwei Seeks je Pfad

        # Shortcuts
        QShortcut(Qt.Key_Space, self, activated=self.on_toggle_play)
        QShortcut(Qt.Key_Delete, self, activated=self.on_remove)
        QShortcut(Qt.Key_I, self, activated=self.mark_in)
        QShortcut(Qt.Key_O, self, activated=self.mark_out)
        QShortcut(Qt.Key_S, self, activated=self.split_at_playhead)

        # ----- VLC AudioEngine -----
        # Ruhiger/robuster starten (weniger Console-Noise)
        self.vlc_instance = vlc.Instance("--no-xlib", "--novideo", "--quiet", "--file-caching=150")
        self.audio_players: Dict[str, vlc.MediaPlayer] = {}
        self.video_players: Dict[str, vlc.MediaPlayer] = {}

        self.statusBar().showMessage("Frame-Preview: Audio via VLC", 3000)

        # Timeline Scene & View
        self.scene = TimelineScene(self.pps)
        self.timeline = TimelineView(self.scene)
        self.timeline.time_changed.connect(self.seek)

        # Frame preview
        self.video_widget = QtWidgets.QLabel("Frame Preview")
        self.video_widget.setAlignment(Qt.AlignCenter)
        self.video_widget.setMinimumHeight(300)

        # Frame thread
        self.frame_thread = FramePreviewer()
        self.frame_thread.frame_ready.connect(self._on_frame_ready)
        self.frame_thread.frame_error.connect(self._on_frame_error)
        self.frame_thread.start()

        # Clip list
        self.list_clips = QtWidgets.QListWidget()
        self.list_clips.currentRowChanged.connect(self.on_select_clip)

        # Audio list
        self.list_audio = QtWidgets.QListWidget()
        self.list_audio.currentRowChanged.connect(self.on_select_audio)

        # Inspector (Video)
        self.lbl_path = QtWidgets.QLabel("-")
        self.lbl_duration = QtWidgets.QLabel("-")
        self.spin_trim_in = QtWidgets.QDoubleSpinBox()
        self._setup_spin(self.spin_trim_in)
        self.spin_trim_out = QtWidgets.QDoubleSpinBox()
        self._setup_spin(self.spin_trim_out)
        self.spin_start = QtWidgets.QDoubleSpinBox()
        self._setup_spin(self.spin_start)
        self.btn_apply_clip = QtWidgets.QPushButton("Übernehmen")
        self.btn_apply_clip.clicked.connect(self.on_apply_from_inspector)

        # Inspector (Audio)
        self.lbl_apath = QtWidgets.QLabel("-")
        self.lbl_adur = QtWidgets.QLabel("-")
        self.spin_ain = QtWidgets.QDoubleSpinBox()
        self._setup_spin(self.spin_ain)
        self.spin_aout = QtWidgets.QDoubleSpinBox()
        self._setup_spin(self.spin_aout)
        self.spin_astart = QtWidgets.QDoubleSpinBox()
        self._setup_spin(self.spin_astart)
        self.spin_again = QtWidgets.QDoubleSpinBox()
        self.spin_again.setRange(-60.0, 24.0)
        self.spin_again.setDecimals(1)
        self.spin_again.setSingleStep(0.5)
        self.btn_apply_audio = QtWidgets.QPushButton("Übernehmen")
        self.btn_apply_audio.clicked.connect(self.on_apply_audio)

        # Toolbar
        tb = self.addToolBar("Main")

        # Datei-Aktionen zuerst
        self.action_new = tb.addAction("Neu")
        self.action_new.triggered.connect(self.on_new_project)
        self.action_open = tb.addAction("Öffnen")
        self.action_open.triggered.connect(self.on_open_project)
        self.action_save = tb.addAction("Speichern")
        self.action_save.triggered.connect(self.on_save_project)

        tb.addSeparator()

        # Import / Entfernen
        self.action_import = tb.addAction("Import Video")
        self.action_import.triggered.connect(self.on_import)
        self.action_import_audio = tb.addAction("Import Audio")
        self.action_import_audio.triggered.connect(self.on_import_audio)
        self.action_remove = tb.addAction("Entfernen")
        self.action_remove.triggered.connect(self.on_remove)

        tb.addSeparator()

        # Play Controls
        self.action_play = tb.addAction("▶︎")
        self.action_play.triggered.connect(self.on_toggle_play)
        self.action_audio_toggle = tb.addAction("Audio: AN")
        self.action_audio_toggle.setCheckable(True)
        self.action_audio_toggle.setChecked(True)
        self.action_audio_toggle.triggered.connect(self.on_toggle_audio_enabled)

        tb.addSeparator()

        self.action_mark_in = tb.addAction("Mark In")
        self.action_mark_in.triggered.connect(self.mark_in)
        self.action_mark_out = tb.addAction("Mark Out")
        self.action_mark_out.triggered.connect(self.mark_out)
        self.action_split = tb.addAction("Split")
        self.action_split.triggered.connect(self.split_at_playhead)

        tb.addSeparator()

        # Timeline Info
        self.lbl_time = QtWidgets.QLabel("00:00.00")
        tb.addWidget(self.lbl_time)

        tb.addSeparator()

        # Preview Settings
        tb.addWidget(QtWidgets.QLabel("Preview FPS:"))
        self.combo_preview_fps = QtWidgets.QComboBox()
        self.combo_preview_fps.addItems(["15", "30", "60", "120"])
        self.combo_preview_fps.setCurrentText("30")
        self.combo_preview_fps.currentTextChanged.connect(self.on_preview_fps_changed)
        tb.addWidget(self.combo_preview_fps)

        tb.addSeparator()

        # Render / Export
        self.action_render_settings = tb.addAction("Render Settings")
        self.action_render_settings.triggered.connect(self.on_open_render_settings)

        tb.addWidget(QtWidgets.QLabel("Export:"))
        self.out_path = QtWidgets.QLineEdit("simpledit-export.mp4")
        self.out_path.setMaximumWidth(240)
        tb.addWidget(self.out_path)

        self.action_export = tb.addAction("Export")
        self.action_export.triggered.connect(self.on_export)

        # Layouts
        splitter = QtWidgets.QSplitter(Qt.Horizontal)

        # Left panel
        left_panel = QtWidgets.QTabWidget()
        left_panel.addTab(self.list_clips, "Clips")
        left_panel.addTab(self.list_audio, "Audio")

        # Right panel (Inspector)
        inspector = QtWidgets.QTabWidget()

        # Video inspector
        wv = QtWidgets.QWidget()
        lv = QtWidgets.QFormLayout(wv)
        lv.addRow("Pfad:", self.lbl_path)
        lv.addRow("Dauer:", self.lbl_duration)
        lv.addRow("Trim In:", self.spin_trim_in)
        lv.addRow("Trim Out:", self.spin_trim_out)
        lv.addRow("Startzeit:", self.spin_start)
        lv.addRow(self.btn_apply_clip)
        inspector.addTab(wv, "Video")

        # Audio inspector
        wa = QtWidgets.QWidget()
        la = QtWidgets.QFormLayout(wa)
        la.addRow("Pfad:", self.lbl_apath)
        la.addRow("Dauer:", self.lbl_adur)
        la.addRow("Trim In:", self.spin_ain)
        la.addRow("Trim Out:", self.spin_aout)
        la.addRow("Startzeit:", self.spin_astart)
        la.addRow("Gain (dB):", self.spin_again)
        la.addRow(self.btn_apply_audio)
        inspector.addTab(wa, "Audio")

                # --- Effects inspector (per-clip) ---
        we = QtWidgets.QWidget()
        le = QtWidgets.QVBoxLayout(we)
        le.setContentsMargins(8, 8, 8, 8)

        # Oben: aktuelle Effekte (Liste in Reihenfolge)
        self.list_effects = QtWidgets.QListWidget()
        self.list_effects.setSelectionMode(QtWidgets.QAbstractItemView.SingleSelection)
        self.list_effects.setDragDropMode(QtWidgets.QAbstractItemView.NoDragDrop)
        le.addWidget(QtWidgets.QLabel("Clip Effects (top → bottom):"))
        le.addWidget(self.list_effects, 1)

        # Mitte: Buttons Up / Down / Remove
        row_btns = QtWidgets.QHBoxLayout()
        self.btn_eff_up = QtWidgets.QPushButton("↑")
        self.btn_eff_down = QtWidgets.QPushButton("↓")
        self.btn_eff_remove = QtWidgets.QPushButton("Remove")
        row_btns.addWidget(self.btn_eff_up)
        row_btns.addWidget(self.btn_eff_down)
        row_btns.addStretch(1)
        row_btns.addWidget(self.btn_eff_remove)
        le.addLayout(row_btns)

        # Unten: Add-Combobox + Add-Button
        row_add = QtWidgets.QHBoxLayout()
        self.combo_eff_add = QtWidgets.QComboBox()
        self.combo_eff_add.addItems(list(AVAILABLE_EFFECTS.values()))
        self.btn_eff_add = QtWidgets.QPushButton("Add")
        row_add.addWidget(self.combo_eff_add, 1)
        row_add.addWidget(self.btn_eff_add)
        le.addLayout(row_add)

        inspector.addTab(we, "Effects")

        # Signals
        self.btn_eff_add.clicked.connect(self.on_effect_add)
        self.btn_eff_remove.clicked.connect(self.on_effect_remove)
        self.btn_eff_up.clicked.connect(self.on_effect_move_up)
        self.btn_eff_down.clicked.connect(self.on_effect_move_down)
        self.list_effects.itemSelectionChanged.connect(self._update_effect_buttons_enabled)


        splitter.addWidget(left_panel)

        # Center panel (video preview + timeline)
        center_panel = QtWidgets.QSplitter(Qt.Vertical)
        center_panel.addWidget(self.video_widget)
        center_panel.addWidget(self.timeline)
        splitter.addWidget(center_panel)

        splitter.addWidget(inspector)

        self.setCentralWidget(splitter)

        # Play timer
        self.play_timer = QTimer(self)
        self.play_timer.setInterval(16)
        self.play_timer.timeout.connect(self._tick_playback)

        # interne Sortier-Listen initialisieren
        self._rebuild_sorted()

    # ----------------- VLC Audio Helpers -----------------
    def _ensure_audio_player(self, audio: AudioItem) -> vlc.MediaPlayer:
        if audio.path not in self.audio_players:
            media = self.vlc_instance.media_new(audio.path)
            p = self.vlc_instance.media_player_new()
            p.set_media(media)
            p.audio_set_volume(80)
            self.audio_players[audio.path] = p
        return self.audio_players[audio.path]

    def _ensure_video_player(self, clip: ClipItem) -> vlc.MediaPlayer:
        if clip.path not in self.video_players:
            media = self.vlc_instance.media_new(clip.path)
            p = self.vlc_instance.media_player_new()
            p.set_media(media)
            p.audio_set_volume(80)
            self.video_players[clip.path] = p
        return self.video_players[clip.path]

    def _stop_all_audio(self):
        for p in list(self.audio_players.values()) + list(self.video_players.values()):
            try:
                p.stop()
            except:
                pass
        self._active_paths.clear()

    # ----------------- Zielzustand bestimmen & anwenden -----------------
    def _recompute_active_targets(self, t: float) -> Dict[str, int]:
        """
        Liefert {path: offset_ms} für alle Quellen (Video-Audio + Extra-Audio),
        die zum Zeitpunkt t aktiv sein sollen.
        """
        targets: Dict[str, int] = {}

        for c in self.clips:
            if c.start_time <= t < c.start_time + c.trimmed_length():
                off_ms = int(((t - c.start_time) + c.trim_in) * 1000)
                targets[c.path] = off_ms

        for a in self.audios:
            if a.start_time <= t < a.start_time + a.trimmed_length():
                off_ms = int(((t - a.start_time) + a.trim_in) * 1000)
                targets[a.path] = off_ms

        return targets

    def _need_seek(self, path: str, desired_ms: int) -> bool:
        """
        Entscheidet, ob wir für 'path' wirklich einen neuen seek auslösen müssen,
        basierend auf letzter gesetzter Zeit & einem Minimalintervall.
        """
        now_ms = QtCore.QTime.currentTime().msecsSinceStartOfDay()
        last_wall = self._last_seek_wall_ms.get(path, -10_000)
        if now_ms - last_wall < self._seek_min_interval_ms:
            return False

        last_set = self._last_seek_by_path.get(path, None)
        if last_set is None:
            return True
        return abs(desired_ms - last_set) > self._seek_guard_ms

    def _seek_player(self, player: vlc.MediaPlayer, path: str, desired_ms: int):
        try:
            # VLC braucht play() bevor set_time() zuverlässig wirkt
            player.play()
            QtCore.QTimer.singleShot(
                60, lambda pl=player, p=path, ms=desired_ms: self._finish_seek(pl, p, ms)
            )
        except:
            pass

    def _finish_seek(self, player: vlc.MediaPlayer, path: str, ms: int):
        try:
            player.set_time(ms)
            self._last_seek_by_path[path] = ms
            self._last_seek_wall_ms[path] = QtCore.QTime.currentTime().msecsSinceStartOfDay()
        except:
            pass

    def _apply_targets(self, targets: Dict[str, int], force: bool = False):
        """
        Wendet den Zielzustand an:
        - stoppt Player, die nicht mehr aktiv sind
        - startet/seekt Player, die aktiv sein müssen
        - rate-limited & mit Seek-Grenze
        """
        target_paths = set(targets.keys())

        # Stoppe alles, was nicht mehr aktiv ist
        to_stop = self._active_paths - target_paths
        for path in to_stop:
            pl = self.video_players.get(path) or self.audio_players.get(path)
            if pl:
                try: pl.stop()
                except: pass

        # Starte/Seeke, was aktiv sein soll
        for path in target_paths:
            # Player besorgen
            pl = self.video_players.get(path)
            if pl is None:
                ap = self.audio_players.get(path)
                if ap is None:
                    # herausfinden ob es ein Video- oder Audio-Item ist
                    clip = next((c for c in self.clips if c.path == path), None)
                    if clip is not None:
                        pl = self._ensure_video_player(clip)
                    else:
                        aud = next((a for a in self.audios if a.path == path), None)
                        if aud is not None:
                            pl = self._ensure_audio_player(aud)
                else:
                    pl = ap

            if not pl:
                continue

            desired_ms = targets[path]

            # Start-/Seek-Entscheidung
            try:
                playing = pl.is_playing()
            except:
                playing = False

            if force:
                try:
                    pl.stop()
                except:
                    pass
                self._seek_player(pl, path, desired_ms)
            else:
                if not playing:
                    # Neu starten (z.B. wir sind in Clip "reingelaufen")
                    self._seek_player(pl, path, desired_ms)
                else:
                    # Läuft schon → nur seeken, wenn sich's wirklich lohnt
                    if self._need_seek(path, desired_ms):
                        self._seek_player(pl, path, desired_ms)

        # Merke den neuen Aktivsatz
        self._active_paths = target_paths

    # Praktischer Helper für alle Timeline-Änderungen
    def _on_timeline_changed(self, hard: bool = True):
        self._rebuild_sorted()
        if self.playing and self.audio_enabled:
            targets = self._recompute_active_targets(self.current_time)
            self._apply_targets(targets, force=hard)

    # ----------------- Play/Stop -----------------
    def on_toggle_play(self):
        try:
            has_anything = bool(self._clip_at_time(self.current_time) or self._audio_at_time(self.current_time))
            if not has_anything:
                self.statusBar().showMessage("Nix zum Abspielen an dieser Stelle.", 2500)
                self.action_play.setText("▶︎")
                return

            self.playing = not self.playing
            self.action_play.setText("⏸" if self.playing else "▶︎")

            if self.playing:
                self._last_tick_ns = time.perf_counter_ns()
                self.play_timer.start()

                if self.audio_enabled:
                    targets = self._recompute_active_targets(self.current_time)
                    self._apply_targets(targets, force=True)
            else:
                self.play_timer.stop()
                self._last_tick_ns = None
                self._stop_all_audio()
        except Exception as e:
            traceback.print_exc()
            self.statusBar().showMessage(f"Play/Pause-Fehler: {e}", 6000)
            self.playing = False
            self.play_timer.stop()
            self._stop_all_audio()
            self.action_play.setText("▶︎")

    # ----------------- helpers -----------------
    def closeEvent(self, e: QtGui.QCloseEvent):
        try:
            self._stop_all_audio()
            self.frame_thread.stop(); self.frame_thread.quit(); self.frame_thread.wait(800)
        except Exception:
            pass
        return super().closeEvent(e)

    def _setup_spin(self, s: QtWidgets.QDoubleSpinBox):
        s.setDecimals(3); s.setSingleStep(0.05); s.setRange(0.0, 100000.0)

    def _gi_key(self, c: ClipItem) -> int: return id(c)
    def _agi_key(self, a: AudioItem) -> int: return id(a)


    def _current_clip_or_none(self) -> Optional[ClipItem]:
        return self.current_clip()

    def _refresh_effects_ui(self):
        """Liste im Effects-Tab mit dem aktuell selektierten Clip synchronisieren."""
        c = self._current_clip_or_none()
        self.list_effects.clear()
        if not c:
            self._update_effect_buttons_enabled()
            return

        # c.effects ist eine Liste von Dicts: {"type": "...", "params": {...}}
        for ec in (c.effects or []):
            t = ec.get("type", "")
            label = AVAILABLE_EFFECTS.get(t, f"Unknown ({t})")
            item = QtWidgets.QListWidgetItem(label)
            item.setData(Qt.UserRole, ec)  # Original-Dict mitgeben
            self.list_effects.addItem(item)

        self._update_effect_buttons_enabled()

    def _update_effect_buttons_enabled(self):
        has_sel = len(self.list_effects.selectedIndexes()) == 1
        self.btn_eff_remove.setEnabled(has_sel)
        self.btn_eff_up.setEnabled(has_sel and self.list_effects.currentRow() > 0)
        self.btn_eff_down.setEnabled(
            has_sel and 0 <= self.list_effects.currentRow() < (self.list_effects.count() - 1)
        )

    def _apply_effects_preview_refresh(self):
        """Nach Effektänderung die Preview neu triggern."""
        c = self._clip_at_time(self.current_time)
        if c:
            local = c.trim_in + (self.current_time - c.start_time)
            self._request_frame(c.path, local)
        # Wenn gerade Playing → Audio bleibt wie ist; wir ändern nur das Bild.

    # --------- Actions: Add / Remove / Reorder ----------

    def on_effect_add(self):
        c = self._current_clip_or_none()
        if not c:
            return
        eff_label = self.combo_eff_add.currentText().strip()
        eff_key = REVERSE_AVAILABLE_EFFECTS.get(eff_label)
        if not eff_key:
            return
        # Default-Params leer; bei parametrisierbaren Effekten hier Defaults setzen
        c.effects = (c.effects or []) + [{"type": eff_key, "params": {}}]
        self._refresh_effects_ui()
        self._apply_effects_preview_refresh()

    def on_effect_remove(self):
        c = self._current_clip_or_none()
        if not c:
            return
        row = self.list_effects.currentRow()
        if 0 <= row < (len(c.effects or [])):
            del c.effects[row]
            self._refresh_effects_ui()
            self._apply_effects_preview_refresh()

    def on_effect_move_up(self):
        c = self._current_clip_or_none()
        if not c:
            return
        row = self.list_effects.currentRow()
        if 0 < row < len(c.effects or []):
            c.effects[row - 1], c.effects[row] = c.effects[row], c.effects[row - 1]
            self._refresh_effects_ui()
            # alte Auswahl wiederherstellen
            self.list_effects.setCurrentRow(row - 1)
            self._apply_effects_preview_refresh()

    def on_effect_move_down(self):
        c = self._current_clip_or_none()
        if not c:
            return
        row = self.list_effects.currentRow()
        if 0 <= row < len(c.effects or []) - 1:
            c.effects[row + 1], c.effects[row] = c.effects[row], c.effects[row + 1]
            self._refresh_effects_ui()
            self.list_effects.setCurrentRow(row + 1)
            self._apply_effects_preview_refresh()

    # ----------------- Lists/UI -----------------
    def current_clip(self) -> Optional[ClipItem]:
        row = self.list_clips.currentRow()
        if 0 <= row < len(self.clips):
            return self.clips[row]
        return None

    def current_audio(self) -> Optional[AudioItem]:
        row = self.list_audio.currentRow()
        if 0 <= row < len(self.audios):
            return self.audios[row]
        return None

    def refresh_clip_list_labels(self):
        self.list_clips.clear()
        for c in self.clips:
            self.list_clips.addItem(
                f"{os.path.basename(c.path)}  t={c.start_time:.2f}s  [{c.trim_in:.2f}–{c.safe_out():.2f}s]"
            )

    def refresh_audio_list_labels(self):
        self.list_audio.clear()
        for a in self.audios:
            self.list_audio.addItem(
                f"{os.path.basename(a.path)}  t={a.start_time:.2f}s  [{a.trim_in:.2f}–{a.safe_out():.2f}s]  {a.gain_db:+.1f} dB"
            )

    def _rebuild_sorted(self):
        self._sorted_by_start = sorted(self.clips, key=lambda c: c.start_time)
        self._sorted_starts = [c.start_time for c in self._sorted_by_start]
        self._sorted_audio_by_start = sorted(self.audios, key=lambda a: a.start_time)
        self._sorted_audio_starts = [a.start_time for a in self._sorted_audio_by_start]

    # ----------------- project I/O -----------------
    def on_new_project(self):
        if self._confirm_discard():
            self._stop_all_audio()
            self.clips.clear(); self.audios.clear()
            self.graphics_by_clip.clear(); self.audio_graphics_by_clip.clear()
            self.scene.clear(); self.scene = TimelineScene(self.pps); self.timeline.setScene(self.scene)
            self.project_path = None
            self.refresh_clip_list_labels(); self.refresh_audio_list_labels(); self._rebuild_sorted()
            self.statusBar().showMessage("Neues Projekt", 3000)
            self._on_timeline_changed(hard=True)
            self._refresh_effects_ui()


    def on_open_project(self):
        path, _ = QtWidgets.QFileDialog.getOpenFileName(self, "Projekt öffnen", "", "Simpledit (*.sedit.json)")
        if not path: return
        try:
            with open(path, "r", encoding="utf-8") as f: data = json.load(f)
            self.clips = [ClipItem(**c) for c in data.get("clips", [])]
            self.audios = [AudioItem(**a) for a in data.get("audios", [])]
            self.pps = float(data.get("pps", self.pps))
            self.graphics_by_clip.clear(); self.audio_graphics_by_clip.clear()
            self.scene.clear(); self.scene = TimelineScene(self.pps); self.timeline.setScene(self.scene)
            for c in self.clips:
                gi = self.scene.add_clip_item(c); gi.moved.connect(self.on_clip_moved); self.graphics_by_clip[self._gi_key(c)] = gi
            for a in self.audios:
                gi = self.scene.add_audio_item(a); gi.moved.connect(self.on_audio_moved); self.audio_graphics_by_clip[self._agi_key(a)] = gi
            self.refresh_clip_list_labels(); self.refresh_audio_list_labels()
            self.project_path = path; self._rebuild_sorted()
            self.statusBar().showMessage(f"Projekt geladen: {os.path.basename(path)}", 3000)
            self._on_timeline_changed(hard=True)
        except Exception as e:
            QtWidgets.QMessageBox.critical(self, "Laden fehlgeschlagen", str(e))

    def on_save_project(self):
        if not self.project_path:
            self.on_save_project_as(); return
        self._write_project(self.project_path)

    def on_save_project_as(self):
        path, _ = QtWidgets.QFileDialog.getSaveFileName(self, "Projekt speichern", "project.sedit.json", "Simpledit (*.sedit.json)")
        if not path: return
        if not path.endswith(".sedit.json"): path += ".sedit.json"
        self._write_project(path); self.project_path = path

    def _write_project(self, path: str):
        from dataclasses import asdict
        data = {"clips": [asdict(c) for c in self.clips], "audios": [asdict(a) for a in self.audios], "version": "2.4.1", "pps": self.pps}
        with open(path, "w", encoding="utf-8") as f: json.dump(data, f, indent=2, ensure_ascii=False)
        self.statusBar().showMessage(f"Gespeichert: {os.path.basename(path)}", 3000)

    def _confirm_discard(self) -> bool:
        if not self.clips and not self.audios: return True
        return QtWidgets.QMessageBox.question(self, "Projekt verwerfen?", "Aktuelles Projekt verwerfen?") == QtWidgets.QMessageBox.Yes

    # ----------------- import/remove/select -----------------
    def on_import(self):
        paths, _ = QtWidgets.QFileDialog.getOpenFileNames(self, "Videos wählen", "", "Videos (*.mp4 *.mov *.mkv *.avi)")
        if not paths: return
        last_end = max([c.start_time + c.trimmed_length() for c in self.clips], default=0.0)
        for p in paths:
            try:
                clip = VideoFileClip(p); dur = float(clip.duration); clip.close()
            except Exception as e:
                QtWidgets.QMessageBox.critical(self, "Fehler beim Lesen", f"{p}\n\n{e}"); continue
            c = ClipItem(path=p, duration=dur, trim_in=0.0, trim_out=dur, start_time=last_end)
            last_end += c.trimmed_length(); self.clips.append(c)
            gi = self.scene.add_clip_item(c); gi.moved.connect(self.on_clip_moved); self.graphics_by_clip[self._gi_key(c)] = gi
        self.refresh_clip_list_labels()
        self._on_timeline_changed(hard=True)
        if self.list_clips.currentRow() == -1 and self.clips: self.list_clips.setCurrentRow(0)

    def on_import_audio(self):
        paths, _ = QtWidgets.QFileDialog.getOpenFileNames(self, "Audio wählen", "", "Audio (*.mp3 *.wav *.m4a *.aac *.flac)")
        if not paths: return
        last_end = max([a.start_time + a.trimmed_length() for a in self.audios], default=0.0)
        for p in paths:
            try:
                ac = AudioFileClip(p); dur = float(ac.duration); ac.close()
            except Exception as e:
                QtWidgets.QMessageBox.critical(self, "Fehler beim Lesen (Audio)", f"{p}\n\n{e}"); continue
            a = AudioItem(path=p, duration=dur, trim_in=0.0, trim_out=dur, start_time=last_end, gain_db=0.0)
            last_end += a.trimmed_length(); self.audios.append(a)
            gi = self.scene.add_audio_item(a); gi.moved.connect(self.on_audio_moved); self.audio_graphics_by_clip[self._agi_key(a)] = gi
        self.refresh_audio_list_labels()
        self._on_timeline_changed(hard=True)
        if self.list_audio.currentRow() == -1 and self.audios: self.list_audio.setCurrentRow(0)

    def on_remove(self):
        row = self.list_clips.currentRow()
        if 0 <= row < len(self.clips):
            c = self.clips.pop(row)
            # Player dieses Clips stoppen & entsorgen
            pl = self.video_players.pop(c.path, None)
            if pl:
                try: pl.stop()
                except: pass
            self._last_seek_by_path.pop(c.path, None)
            self._last_seek_wall_ms.pop(c.path, None)

            gi = self.graphics_by_clip.pop(self._gi_key(c), None)
            if gi: self.scene.removeItem(gi)

            self.refresh_clip_list_labels()
            self._on_timeline_changed(hard=True)
            return

        rowa = self.list_audio.currentRow()
        if 0 <= rowa < len(self.audios):
            a = self.audios.pop(rowa)
            pl = self.audio_players.pop(a.path, None)
            if pl:
                try: pl.stop()
                except: pass
            self._last_seek_by_path.pop(a.path, None)
            self._last_seek_wall_ms.pop(a.path, None)

            gi = self.audio_graphics_by_clip.pop(self._agi_key(a), None)
            if gi: self.scene.removeItem(gi)

            self.refresh_audio_list_labels()
            self._on_timeline_changed(hard=True)

    def on_select_clip(self, row: int):
        if not (0 <= row < len(self.clips)):
            self.lbl_path.setText("-"); self.lbl_duration.setText("-")
            self.spin_trim_in.setValue(0.0); self.spin_trim_out.setValue(0.0); self.spin_start.setValue(0.0)
            return
        c = self.clips[row]
        self.lbl_path.setText(c.path); self.lbl_duration.setText(f"{c.duration:.3f}s")
        self.spin_trim_in.setMaximum(c.duration); self.spin_trim_out.setMaximum(c.duration)
        self.spin_trim_in.setValue(c.trim_in); self.spin_trim_out.setValue(c.safe_out()); self.spin_start.setValue(c.start_time)
        
        self._request_frame(c.path, c.trim_in)
        self._refresh_effects_ui()

    def on_apply_from_inspector(self):
        c = self.current_clip()
        if not c: return
        ti = float(self.spin_trim_in.value())
        to = float(self.spin_trim_out.value())
        st = float(self.spin_start.value())
        if not (0.0 <= ti < to <= c.duration+1e-6):
            QtWidgets.QMessageBox.warning(self, "Ungültig", "Trim-Werte prüfen: 0 ≤ In < Out ≤ Dauer.")
            return
        c.trim_in, c.trim_out, c.start_time = ti, to, max(0.0, st)
        gi = self.graphics_by_clip.get(self._gi_key(c))
        self._refresh_effects_ui()
        if gi:
            gi.update_geometry(); gi._refresh_label()
        self.refresh_clip_list_labels()
        self._on_timeline_changed(hard=True)
        self._request_frame(c.path, c.trim_in)

    def on_select_audio(self, row: int):
        if not (0 <= row < len(self.audios)):
            self.lbl_apath.setText("-"); self.lbl_adur.setText("-")
            self.spin_ain.setValue(0.0); self.spin_aout.setValue(0.0); self.spin_astart.setValue(0.0); self.spin_again.setValue(0.0)
            return
        a = self.audios[row]
        self.lbl_apath.setText(a.path); self.lbl_adur.setText(f"{a.duration:.3f}s")
        self.spin_ain.setMaximum(a.duration); self.spin_aout.setMaximum(a.duration)
        self.spin_ain.setValue(a.trim_in); self.spin_aout.setValue(a.safe_out())
        self.spin_astart.setValue(a.start_time); self.spin_again.setValue(a.gain_db)

    def on_apply_audio(self):
        a = self.current_audio()
        if not a: return
        ti = float(self.spin_ain.value())
        to = float(self.spin_aout.value())
        st = float(self.spin_astart.value())
        if not (0.0 <= ti < to <= a.duration+1e-6):
            QtWidgets.QMessageBox.warning(self, "Ungültig", "Audio-Trim prüfen: 0 ≤ In < Out ≤ Dauer.")
            return
        a.trim_in, a.trim_out, a.start_time, a.gain_db = ti, to, max(0.0, st), float(self.spin_again.value())
        gi = self.audio_graphics_by_clip.get(self._agi_key(a))
        if gi:
            gi.update_geometry(); gi._refresh_label()
        self.refresh_audio_list_labels()
        self._on_timeline_changed(hard=True)

    def on_remove_audio(self):
        row = self.list_audio.currentRow()
        if not (0 <= row < len(self.audios)): return
        a = self.audios.pop(row)
        gi = self.audio_graphics_by_clip.pop(self._agi_key(a), None)
        if gi: self.scene.removeItem(gi)
        self.refresh_audio_list_labels()
        self._on_timeline_changed(hard=True)
        self._refresh_effects_ui()


    def on_clip_moved(self, clip: ClipItem):
        self.refresh_clip_list_labels()
        self._on_timeline_changed(hard=False)

    def on_audio_moved(self, audio: AudioItem):
        self.refresh_audio_list_labels()
        self._on_timeline_changed(hard=False)

    # ----------------- preview quality -----------------
    def on_preview_quality_changed(self, text: str):
        mapping = {"Auto": 0, "720p": 720, "540p": 540, "360p": 360, "240p": 240, "144p": 144}
        self.preview_height = mapping.get(text, 360)
        c = self._clip_at_time(self.current_time)
        if c:
            local = c.trim_in + (self.current_time - c.start_time)
            self._request_frame(c.path, local)

    def on_preview_fps_changed(self, text: str):
        try:
            self.preview_fps = int(text)
        except ValueError:
            self.preview_fps = 30
        self.statusBar().showMessage(f"Preview FPS: {self.preview_fps}", 1500)

    # ----------------- playback/seek -----------------
    def on_toggle_audio_enabled(self, checked: bool):
        self.audio_enabled = checked
        self.action_audio_toggle.setText("Audio: AN" if checked else "Audio: AUS")
        self.statusBar().showMessage(f"Audio {'aktiv' if checked else 'ausgeschaltet'}", 2000)
        if not checked:
            self._stop_all_audio()
        else:
            if self.playing:
                targets = self._recompute_active_targets(self.current_time)
                self._apply_targets(targets, force=True)

    def _tick_playback(self):
        now_ns = time.perf_counter_ns()
        if getattr(self, "_last_tick_ns", None) is None:
            self._last_tick_ns = now_ns
            return
        dt = (now_ns - self._last_tick_ns) / 1e9
        self._last_tick_ns = now_ns
        if dt < 0:
            dt = 0
        self.seek(self.current_time + dt, from_player=True)

        # Nur wenn playing & audio_enabled → evtl. Set-Änderungen anwenden
        if self.playing and self.audio_enabled:
            targets = self._recompute_active_targets(self.current_time)
            # Wenn sich der aktive Satz ändert → force, sonst NICHT dauernd seeken
            changed = set(targets.keys()) != self._active_paths
            self._apply_targets(targets, force=changed)

    def _clip_at_time(self, t: float) -> Optional[ClipItem]:
        if not getattr(self, "_sorted_by_start", None): return None
        i = bisect.bisect_right(self._sorted_starts, t) - 1
        if i >= 0:
            c = self._sorted_by_start[i]
            if t < c.start_time + c.trimmed_length() - 1e-6: return c
        return None

    def _audio_at_time(self, t: float) -> Optional[AudioItem]:
        if not getattr(self, "_sorted_audio_by_start", None): return None
        i = bisect.bisect_right(self._sorted_audio_starts, t) - 1
        if i >= 0:
            a = self._sorted_audio_by_start[i]
            if t < a.start_time + a.trimmed_length() - 1e-6: return a
        return None

    def seek(self, t: float, from_player: bool=False):
        self.current_time = max(0.0, t)
        self.lbl_time.setText(fmt_time(self.current_time))
        self.scene.update_playhead_x(self.current_time)

        # --- Frame Preview ---
        now_ms = QtCore.QTime.currentTime().msecsSinceStartOfDay()
        if not hasattr(self, "_last_preview_at_ms"):
            self._last_preview_at_ms = -1

        c = self._clip_at_time(self.current_time)
        need_preview = False
        if not from_player:
            need_preview = True
        else:
            interval = int(1000 / self.preview_fps)
            if now_ms - self._last_preview_at_ms >= interval:
                need_preview = True

        if c and need_preview:
            local = c.trim_in + (self.current_time - c.start_time)
            self._request_frame(c.path, local)
            self._last_preview_at_ms = now_ms

        # --- Audio ---
        if self.playing and self.audio_enabled:
            targets = self._recompute_active_targets(self.current_time)
            # Bei User-Seek (from_player=False) → force neu setzen
            self._apply_targets(targets, force=not from_player)

    # ----------------- Frame thread hooks -----------------
    def _request_frame(self, path: str, t_local: float):
        self.frame_thread.request(path, t_local, self.video_widget.width(), self.video_widget.height(), self.preview_height)

    def _on_frame_ready(self, qimg: QtGui.QImage):
        img = qimg

        # Aktiven Clip ermitteln
        c = self._clip_at_time(self.current_time)
        if c and getattr(c, "effects", None):
            from effects import apply_chain_qimage
            try:
                img = apply_chain_qimage(img, c.effects)  # <- WICHTIG: Rückgabe zuweisen
            except Exception as e:
                print("[effects] preview error:", e)

        pix = QtGui.QPixmap.fromImage(img)
        if isinstance(self.video_widget, QtWidgets.QLabel):
            self.video_widget.setPixmap(pix)


    def _on_frame_error(self, msg: str):
        if isinstance(self.video_widget, QtWidgets.QLabel):
            self.video_widget.setText(f"Frame konnte nicht geladen werden:\n{msg}")

    # ----------------- Edit Ops -----------------
    def mark_in(self):
        c = self.current_clip()
        if not c: return
        if not (c.start_time <= self.current_time <= c.start_time + c.trimmed_length()): return
        new_ti = c.trim_in + (self.current_time - c.start_time)
        new_ti = max(0.0, min(new_ti, c.safe_out()-0.05))
        c.trim_in = new_ti
        gi = self.graphics_by_clip.get(self._gi_key(c))
        if gi:
            gi.update_geometry(); gi._refresh_label()
        self.refresh_clip_list_labels()
        self._on_timeline_changed(hard=True)

    def mark_out(self):
        c = self.current_clip()
        if not c: return
        if not (c.start_time <= self.current_time <= c.start_time + c.trimmed_length()): return
        new_to = c.trim_in + (self.current_time - c.start_time)
        new_to = max(c.trim_in+0.05, min(new_to, c.duration))
        c.trim_out = new_to
        gi = self.graphics_by_clip.get(self._gi_key(c))
        if gi:
            gi.update_geometry(); gi._refresh_label()
        self.refresh_clip_list_labels()
        self._on_timeline_changed(hard=True)

    def split_at_playhead(self):
        t = self.current_time
        c = self._clip_at_time(t)
        if c:
            local = c.trim_in + (t - c.start_time); eps = 1e-4
            if c.trim_in + eps < local < c.safe_out() - eps:
                old_out = c.safe_out(); c.trim_out = local
                new_c = ClipItem(path=c.path, duration=c.duration, trim_in=local, trim_out=old_out, start_time=t)
                self.clips.append(new_c)
                gi = self.scene.add_clip_item(new_c); gi.moved.connect(self.on_clip_moved)
                self.graphics_by_clip[self._gi_key(new_c)] = gi
                gi_left = self.graphics_by_clip.get(self._gi_key(c))
                if gi_left:
                    gi_left.update_geometry(); gi_left._refresh_label()
                gi.update_geometry(); gi._refresh_label()
                self.refresh_clip_list_labels()
                self._on_timeline_changed(hard=True)
                return
        a = self._audio_at_time(t)
        if a:
            local = a.trim_in + (t - a.start_time); eps = 1e-4
            if a.trim_in + eps < local < a.safe_out() - eps:
                old_out = a.safe_out(); a.trim_out = local
                new_a = AudioItem(path=a.path, duration=a.duration, trim_in=local, trim_out=old_out, start_time=t, gain_db=a.gain_db)
                self.audios.append(new_a)
                gi = self.scene.add_audio_item(new_a); gi.moved.connect(self.on_audio_moved)
                self.audio_graphics_by_clip[self._agi_key(new_a)] = gi
                gi_left = self.audio_graphics_by_clip.get(self._agi_key(a))
                if gi_left:
                    gi_left.update_geometry(); gi_left._refresh_label()
                gi.update_geometry(); gi._refresh_label()
                self.refresh_audio_list_labels()
                self._on_timeline_changed(hard=True)

    def timeline_length(self) -> float:
        end_v = max([c.start_time + c.trimmed_length() for c in self.clips], default=0.0)
        end_a = max([a.start_time + a.trimmed_length() for a in self.audios], default=0.0)
        return max(end_v, end_a)

    # --------------- Export ---------------
    def on_open_render_settings(self):
        dlg = RenderSettingsDialog(self)
        if dlg.exec() == QtWidgets.QDialog.Accepted:
            self.render_settings = dlg.get_settings()
            self.statusBar().showMessage(f"Render settings updated: {self.render_settings}", 3000)

    def _target_resolution(self, setting: str, default=(1280, 720)):
        mapping = {
            "720p": (1280, 720),
            "1080p": (1920, 1080),
            "1440p": (2560, 1440),
            "4K": (3840, 2160),
        }
        return mapping.get(setting, default)

    def on_export(self):
        if not self.clips and not self.audios:
            QtWidgets.QMessageBox.information(self, "Nix zu exportieren", "Bitte zuerst Clips/Audio einfügen.")
            return

        out = self.out_path.text().strip() or "simpledit-export.mp4"

        try:
            # Sequenz bauen
            final = self._render_moviepy_sequence()

            # Render Settings
            settings = self.render_settings
            codec = "libx264" if "264" in settings["codec"] else \
                    "libx265" if "265" in settings["codec"] else \
                    "prores" if "prores" in settings["codec"] else "vp9"

            final.write_videofile(
                out,
                codec=codec,
                audio_codec="aac",
                audio_bitrate=settings["audio_bitrate"],
                preset=settings["preset"],
                fps=None if settings["fps"] == "Auto" else int(settings["fps"]),
                threads=0,
                temp_audiofile="~temp-audio.m4a",
                remove_temp=True,
                logger=None,
            )

            try:
                final.close()
            except:
                pass

            QtWidgets.QMessageBox.information(self, "Fertig", f"Export geschrieben: {os.path.abspath(out)}")

        except Exception as e:
            QtWidgets.QMessageBox.critical(self, "Export-Fehler", str(e))

    def _render_moviepy_sequence(self):
        ordered_v = self._sorted_by_start
        v_segments = []
        t_cursor = 0.0
        for c in ordered_v:
            if c.start_time > t_cursor + 1e-6:
                gap = c.start_time - t_cursor
                v_segments.append(ColorClip(size=(1280, 720), color=(0, 0, 0), duration=gap))
                t_cursor += gap
            base = VideoFileClip(c.path)
            sub = make_subclip(base, c.trim_in, c.safe_out())
            # NEW: apply per-clip effects (MoviePy)
            try:
                effect_cfgs = [EffectConfig(**ec) for ec in (getattr(c, "effects", []) or [])]
                for eff in build_chain(effect_cfgs):
                    sub = eff.apply_moviepy(sub)
            except Exception as _e:
                print(_e)
                pass
            v_segments.append(sub)
            t_cursor += c.trimmed_length()

        if not v_segments:
            total = self.timeline_length()
            video = ColorClip(size=(1280, 720), color=(0, 0, 0), duration=max(0.1, total))
        else:
            video = v_segments[0] if len(v_segments) == 1 else concatenate_videoclips(v_segments, method="compose")

        # --- Audio hinzufügen ---
        extra_audio_clips = []
        for a in self._sorted_audio_by_start:
            ac = make_audio_subclip(AudioFileClip(a.path), a.trim_in, a.safe_out())
            if abs(a.gain_db) > 1e-6:
                ac = ac.volumex(10 ** (a.gain_db / 20.0))
            ac = set_start_compat(ac, a.start_time)
            extra_audio_clips.append(ac)

        if extra_audio_clips:
            tracks = []
            if video.audio is not None:
                tracks.append(video.audio)
            tracks.extend(extra_audio_clips)
            comp = CompositeAudioClip(tracks)
            video = set_audio_compat(video, comp)

        # --- Resolution anwenden ---
        settings = self.render_settings
        if settings["resolution"] != "Auto":
            target_w, target_h = self._target_resolution(settings["resolution"])
            video = video.resized(new_size=(target_w, target_h))

        return video
