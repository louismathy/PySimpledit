from typing import List, Optional

from PySide6 import QtWidgets, QtCore
from PySide6.QtGui import QShortcut
from PySide6.QtCore import Qt, QTimer

from audio_engine import AudioEngine
from editor_core import EditorCoreMixin
from editor_effects import EditorEffectsMixin, AVAILABLE_EFFECTS
from editor_export import EditorExportMixin
from editor_playback import EditorPlaybackMixin
from editor_project import EditorProjectMixin
from editor_selection import EditorSelectionMixin
from models import ClipItem, AudioItem
from preview import FramePreviewer
from timeline import TimelineScene, TimelineView
from timeline_mixer import TimelineMixer


class EditorMainWindow(
    EditorCoreMixin,
    EditorEffectsMixin,
    EditorProjectMixin,
    EditorSelectionMixin,
    EditorPlaybackMixin,
    EditorExportMixin,
    QtWidgets.QMainWindow,
):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Simpledit - Timeline Editor")
        self.resize(1440, 880)

        self.pps = 80.0
        self.clips: List[ClipItem] = []
        self.audios: List[AudioItem] = []
        self.graphics_by_clip: dict[int, object] = {}
        self.audio_graphics_by_clip: dict[int, object] = {}
        self.project_path: Optional[str] = None
        self.current_time: float = 0.0
        self.playing = False
        self.audio_enabled = True
        self.preview_height = 360
        self.preview_fps = 30
        self.render_settings = {
            "resolution": "Auto",
            "fps": "Auto",
            "codec": "libx264 (H.264)",
            "preset": "medium",
            "audio_bitrate": "192k",
        }

        self.audio_sr = 48000
        self.audio_ch = 2
        self.audio_block = 1024
        self.mixer = TimelineMixer(lambda: self.clips, lambda: self.audios,
                                   sample_rate=self.audio_sr, channels=self.audio_ch)
        self.audio_engine = AudioEngine(sample_rate=self.audio_sr, channels=self.audio_ch, blocksize=self.audio_block)
        self.audio_engine.set_timeline_callback(self.mixer.render_block)

        self.scene = TimelineScene(self.pps)
        self.timeline = TimelineView(self.scene)
        self.timeline.time_changed.connect(self.seek)
        self.scene.selectionChanged.connect(self._on_scene_selection_changed)
        self._last_selection_kind: Optional[str] = None

        self.video_widget = QtWidgets.QLabel("Frame Preview")
        self.video_widget.setAlignment(Qt.AlignCenter)
        self.video_widget.setMinimumHeight(300)

        self.frame_thread = FramePreviewer()
        self.frame_thread.frame_ready.connect(self._on_frame_ready)
        self.frame_thread.frame_error.connect(self._on_frame_error)
        self.frame_thread.start()

        self.list_clips = QtWidgets.QListWidget()
        self.list_clips.currentRowChanged.connect(self.on_select_clip)

        self.list_audio = QtWidgets.QListWidget()
        self.list_audio.currentRowChanged.connect(self.on_select_audio)

        self.lbl_path = QtWidgets.QLabel("-")
        self.lbl_duration = QtWidgets.QLabel("-")
        self.spin_trim_in = QtWidgets.QDoubleSpinBox()
        self._setup_spin(self.spin_trim_in)
        self.spin_trim_out = QtWidgets.QDoubleSpinBox()
        self._setup_spin(self.spin_trim_out)
        self.spin_start = QtWidgets.QDoubleSpinBox()
        self._setup_spin(self.spin_start)
        self.btn_apply_clip = QtWidgets.QPushButton("Apply")
        self.btn_apply_clip.clicked.connect(self.on_apply_from_inspector)

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
        self.btn_apply_audio = QtWidgets.QPushButton("Apply")
        self.btn_apply_audio.clicked.connect(self.on_apply_audio)

        tb = self.addToolBar("Main")

        self.action_new = tb.addAction("New")
        self.action_new.triggered.connect(self.on_new_project)
        self.action_open = tb.addAction("Open")
        self.action_open.triggered.connect(self.on_open_project)
        self.action_save = tb.addAction("Save")
        self.action_save.triggered.connect(self.on_save_project)

        tb.addSeparator()

        self.action_import = tb.addAction("Import Video")
        self.action_import.triggered.connect(self.on_import)
        self.action_import_audio = tb.addAction("Import Audio")
        self.action_import_audio.triggered.connect(self.on_import_audio)
        self.action_remove = tb.addAction("Remove")
        self.action_remove.triggered.connect(self.on_remove)

        tb.addSeparator()

        self.action_play = tb.addAction("Play")
        self.action_play.triggered.connect(self.on_toggle_play)
        self.action_audio_toggle = tb.addAction("Audio: On")
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

        self.lbl_time = QtWidgets.QLabel("00:00.00")
        tb.addWidget(self.lbl_time)

        tb.addSeparator()

        tb.addWidget(QtWidgets.QLabel("Preview FPS:"))
        self.combo_preview_fps = QtWidgets.QComboBox()
        self.combo_preview_fps.addItems(["15", "30", "60", "120"])
        self.combo_preview_fps.setCurrentText("30")
        self.combo_preview_fps.currentTextChanged.connect(self.on_preview_fps_changed)
        tb.addWidget(self.combo_preview_fps)

        tb.addSeparator()

        self.action_render_settings = tb.addAction("Render Settings")
        self.action_render_settings.triggered.connect(self.on_open_render_settings)

        tb.addWidget(QtWidgets.QLabel("Export:"))
        self.out_path = QtWidgets.QLineEdit("simpledit-export.mp4")
        self.out_path.setMaximumWidth(240)
        tb.addWidget(self.out_path)

        self.action_export = tb.addAction("Export")
        self.action_export.triggered.connect(self.on_export)

        splitter = QtWidgets.QSplitter(Qt.Horizontal)

        left_panel = QtWidgets.QTabWidget()
        left_panel.addTab(self.list_clips, "Clips")
        left_panel.addTab(self.list_audio, "Audio")

        inspector = QtWidgets.QTabWidget()

        wv = QtWidgets.QWidget()
        lv = QtWidgets.QFormLayout(wv)
        lv.addRow("Path:", self.lbl_path)
        lv.addRow("Duration:", self.lbl_duration)
        lv.addRow("Trim In:", self.spin_trim_in)
        lv.addRow("Trim Out:", self.spin_trim_out)
        lv.addRow("Start Time:", self.spin_start)
        lv.addRow(self.btn_apply_clip)
        inspector.addTab(wv, "Video")

        wa = QtWidgets.QWidget()
        la = QtWidgets.QFormLayout(wa)
        la.addRow("Path:", self.lbl_apath)
        la.addRow("Duration:", self.lbl_adur)
        la.addRow("Trim In:", self.spin_ain)
        la.addRow("Trim Out:", self.spin_aout)
        la.addRow("Start Time:", self.spin_astart)
        la.addRow("Gain (dB):", self.spin_again)
        la.addRow(self.btn_apply_audio)
        inspector.addTab(wa, "Audio")

        we = QtWidgets.QWidget()
        le = QtWidgets.QVBoxLayout(we)
        le.setContentsMargins(8, 8, 8, 8)

        self.list_effects = QtWidgets.QListWidget()
        self.list_effects.setSelectionMode(QtWidgets.QAbstractItemView.SingleSelection)
        self.list_effects.setDragDropMode(QtWidgets.QAbstractItemView.NoDragDrop)
        le.addWidget(QtWidgets.QLabel("Clip Effects (top to bottom):"))
        le.addWidget(self.list_effects, 1)

        row_btns = QtWidgets.QHBoxLayout()
        self.btn_eff_up = QtWidgets.QPushButton("Up")
        self.btn_eff_down = QtWidgets.QPushButton("Down")
        self.btn_eff_remove = QtWidgets.QPushButton("Remove")
        row_btns.addWidget(self.btn_eff_up)
        row_btns.addWidget(self.btn_eff_down)
        row_btns.addStretch(1)
        row_btns.addWidget(self.btn_eff_remove)
        le.addLayout(row_btns)

        row_add = QtWidgets.QHBoxLayout()
        self.combo_eff_add = QtWidgets.QComboBox()
        self.combo_eff_add.addItems(list(AVAILABLE_EFFECTS.values()))
        self.btn_eff_add = QtWidgets.QPushButton("Add")
        row_add.addWidget(self.combo_eff_add, 1)
        row_add.addWidget(self.btn_eff_add)
        le.addLayout(row_add)

        inspector.addTab(we, "Effects")

        self.btn_eff_add.clicked.connect(self.on_effect_add)
        self.btn_eff_remove.clicked.connect(self.on_effect_remove)
        self.btn_eff_up.clicked.connect(self.on_effect_move_up)
        self.btn_eff_down.clicked.connect(self.on_effect_move_down)
        self.list_effects.itemSelectionChanged.connect(self._update_effect_buttons_enabled)

        splitter.addWidget(left_panel)

        center_panel = QtWidgets.QSplitter(Qt.Vertical)
        center_panel.addWidget(self.video_widget)
        center_panel.addWidget(self.timeline)
        splitter.addWidget(center_panel)

        splitter.addWidget(inspector)

        self.setCentralWidget(splitter)

        QShortcut(Qt.Key_Space, self, activated=self.on_toggle_play)
        QShortcut(Qt.Key_Delete, self, activated=self.on_remove)
        QShortcut(Qt.Key_I, self, activated=self.mark_in)
        QShortcut(Qt.Key_O, self, activated=self.mark_out)
        QShortcut(Qt.Key_S, self, activated=self.split_at_playhead)

        self.play_timer = QTimer(self)
        self.play_timer.setInterval(16)
        self.play_timer.timeout.connect(self._tick_playback)

        self._rebuild_sorted()

        QtCore.QTimer.singleShot(0, self._jump_to_start)
