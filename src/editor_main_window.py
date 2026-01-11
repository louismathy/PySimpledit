from typing import List, Optional

from PySide6 import QtWidgets, QtCore, QtGui
from PySide6.QtGui import QShortcut
from PySide6.QtCore import Qt, QTimer

from audio_engine import AudioEngine
from editor_core import EditorCoreMixin
from editor_effects import EditorEffectsMixin, AVAILABLE_EFFECTS
from editor_export import EditorExportMixin
from editor_icons import load_tinted_icon
from editor_playback import EditorPlaybackMixin
from editor_project import EditorProjectMixin
from editor_selection import EditorSelectionMixin
from editor_thumbnails import ThumbnailSignals
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

        self._icons: dict[str, QtGui.QIcon] = {}
        self._thumb_cache: dict[str, QtGui.QPixmap] = {}
        self._thumb_inflight: set[str] = set()
        self._thumb_signals = ThumbnailSignals()
        self._thumb_signals.ready.connect(self._on_thumbnail_ready)
        self._thumb_pool = QtCore.QThreadPool()
        self._theme_mode = "dark"

        self.audio_sr = 48000
        self.audio_ch = 2
        self.audio_block = 1024
        self.mixer = TimelineMixer(lambda: self.clips, lambda: self.audios,
                                   sample_rate=self.audio_sr, channels=self.audio_ch)
        self.audio_engine = AudioEngine(sample_rate=self.audio_sr, channels=self.audio_ch, blocksize=self.audio_block)
        self.audio_engine.set_timeline_callback(self.mixer.render_block)

        self.scene = TimelineScene(self.pps)
        self.timeline = TimelineView(self.scene)
        self.timeline.setObjectName("timelineView")
        self.timeline.time_changed.connect(self.seek)
        self.scene.selectionChanged.connect(self._on_scene_selection_changed)
        self._last_selection_kind: Optional[str] = None

        self.video_widget = QtWidgets.QLabel("Frame Preview")
        self.video_widget.setObjectName("videoPreview")
        self.video_widget.setAlignment(Qt.AlignCenter)
        self.video_widget.setMinimumHeight(300)
        self.video_widget.setScaledContents(True)
        self.video_widget.setSizePolicy(QtWidgets.QSizePolicy.Ignored, QtWidgets.QSizePolicy.Ignored)

        self.frame_thread = FramePreviewer()
        self.frame_thread.frame_ready.connect(self._on_frame_ready)
        self.frame_thread.frame_error.connect(self._on_frame_error)
        self.frame_thread.start()

        self.list_clips = QtWidgets.QListWidget()
        self.list_clips.setObjectName("clipList")
        self.list_clips.setIconSize(QtCore.QSize(112, 63))
        self.list_clips.setSpacing(8)
        self.list_clips.setUniformItemSizes(True)
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
        tb.setMovable(False)
        tb.setToolButtonStyle(Qt.ToolButtonTextUnderIcon)
        tb.setIconSize(QtCore.QSize(32, 32))

        self.action_new = tb.addAction("New")
        self._set_action_icon(self.action_new, "new_project.png")
        self.action_new.triggered.connect(self.on_new_project)
        self.action_open = tb.addAction("Open")
        self._set_action_icon(self.action_open, "open_project.png")
        self.action_open.triggered.connect(self.on_open_project)
        self.action_save = tb.addAction("Save")
        self._set_action_icon(self.action_save, "save_project.png")
        self.action_save.triggered.connect(self.on_save_project)

        tb.addSeparator()

        self.action_import = tb.addAction("Import Video")
        self._set_action_icon(self.action_import, "import_video.png")
        self.action_import.triggered.connect(self.on_import)
        self.action_import_audio = tb.addAction("Import Audio")
        self._set_action_icon(self.action_import_audio, "import_audio.png")
        self.action_import_audio.triggered.connect(self.on_import_audio)
        self.action_remove = tb.addAction("Remove")
        self._set_action_icon(self.action_remove, "remove.png")
        self.action_remove.triggered.connect(self.on_remove)

        tb.addSeparator()

        self.action_play = tb.addAction("Play")
        self._set_action_icon(self.action_play, "play.png")
        self.action_play.triggered.connect(self.on_toggle_play)
        self.action_audio_toggle = tb.addAction("Audio: On")
        self._set_action_icon(self.action_audio_toggle, "audio_on.png")
        self.action_audio_toggle.setCheckable(True)
        self.action_audio_toggle.setChecked(True)
        self.action_audio_toggle.triggered.connect(self.on_toggle_audio_enabled)

        tb.addSeparator()

        self.action_split = tb.addAction("Split")
        self._set_action_icon(self.action_split, "split.png")
        self.action_split.triggered.connect(self.split_at_playhead)

        tb.addSeparator()

        self.lbl_time = QtWidgets.QLabel("00:00.00")
        tb.addWidget(self.lbl_time)

        tb.addSeparator()

        fps_label = QtWidgets.QLabel("Preview FPS:")
        fps_icon = self._get_icon("preview_fps.png")
        if fps_icon:
            fps_label.setPixmap(fps_icon.pixmap(18, 18))
            fps_label.setToolTip("Preview FPS")
        tb.addWidget(fps_label)
        self.combo_preview_fps = QtWidgets.QComboBox()
        self.combo_preview_fps.addItems(["15", "30", "60", "120"])
        self.combo_preview_fps.setCurrentText("30")
        self.combo_preview_fps.currentTextChanged.connect(self.on_preview_fps_changed)
        tb.addWidget(self.combo_preview_fps)

        tb.addSeparator()

        self.action_render_settings = tb.addAction("Render Settings")
        self._set_action_icon(self.action_render_settings, "render_settings.png")
        self.action_render_settings.triggered.connect(self.on_open_render_settings)

        tb.addWidget(QtWidgets.QLabel("Export:"))
        self.out_path = QtWidgets.QLineEdit("simpledit-export.mp4")
        self.out_path.setMaximumWidth(240)
        tb.addWidget(self.out_path)

        self.action_export = tb.addAction("Export")
        self._set_action_icon(self.action_export, "export.png")
        self.action_export.triggered.connect(self.on_export)

        tb.addSeparator()
        self.action_theme_toggle = tb.addAction("Dark Mode")
        self.action_theme_toggle.setCheckable(True)
        self.action_theme_toggle.setChecked(True)
        self._set_theme_icon()
        self.action_theme_toggle.triggered.connect(self._toggle_theme_mode)

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
        self.list_effects.setObjectName("effectsList")
        self.list_effects.setSelectionMode(QtWidgets.QAbstractItemView.SingleSelection)
        self.list_effects.setDragDropMode(QtWidgets.QAbstractItemView.NoDragDrop)
        self.list_effects.setSpacing(6)
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
        self.list_effects.itemClicked.connect(self._on_effect_item_clicked)
        self.list_effects.itemSelectionChanged.connect(self._update_effect_buttons_enabled)

        splitter.addWidget(left_panel)

        center_panel = QtWidgets.QSplitter(Qt.Vertical)
        center_panel.addWidget(self.video_widget)
        center_panel.addWidget(self.timeline)
        splitter.addWidget(center_panel)

        splitter.addWidget(inspector)

        self.setCentralWidget(splitter)

        self._apply_theme("dark")
        self._setup_window_effects()

        QShortcut(Qt.Key_Space, self, activated=self.on_toggle_play)
        QShortcut(Qt.Key_Delete, self, activated=self.on_remove)
        QShortcut(Qt.Key_S, self, activated=self.split_at_playhead)

        self.play_timer = QTimer(self)
        self.play_timer.setInterval(16)
        self.play_timer.timeout.connect(self._tick_playback)

        self._rebuild_sorted()

        QtCore.QTimer.singleShot(0, self._jump_to_start)

    def _set_action_icon(self, action: QtGui.QAction, filename: str):
        icon = self._get_icon(filename)
        if icon:
            action.setIcon(icon)

    def _get_icon(self, filename: str) -> QtGui.QIcon | None:
        if filename not in self._icons:
            icon = load_tinted_icon(filename, size=QtCore.QSize(32, 32))
            if icon:
                self._icons[filename] = icon
        return self._icons.get(filename)

    def _apply_theme(self, mode: str):
        base_font = QtGui.QFont("SF Pro Display", 10)
        QtWidgets.QApplication.instance().setFont(base_font)

        if mode == "dark":
            self.setStyleSheet(
                """
                QMainWindow {
                    background: #141821;
                    color: #E6EDF7;
                }
                QLabel, QToolButton, QTabBar::tab, QListWidget, QLineEdit, QComboBox, QDoubleSpinBox {
                    color: #E6EDF7;
                }
                QToolBar {
                    background: #1B2130;
                    border-bottom: 1px solid #2A3345;
                    spacing: 6px;
                    padding: 6px;
                }
                QToolButton {
                    background: transparent;
                    border-radius: 12px;
                    padding: 6px 10px;
                }
                QToolButton:hover {
                    background: #243149;
                }
                QToolButton:pressed {
                    background: #2D3A55;
                }
                QToolButton:checked {
                    background: #2A3956;
                }
                QTabWidget::pane {
                    border: 1px solid #2A3345;
                    border-radius: 14px;
                    background: #1B2130;
                }
                QTabBar::tab {
                    background: #202737;
                    border-radius: 10px;
                    padding: 6px 12px;
                    margin: 4px;
                }
                QTabBar::tab:selected {
                    background: #1B2130;
                    border: 1px solid #2F3C55;
                }
                QListWidget {
                    background: #1B2130;
                    border: 1px solid #2A3345;
                    border-radius: 12px;
                    padding: 6px;
                }
                QListWidget::item {
                    border-radius: 10px;
                    padding: 6px;
                }
                QListWidget::item:selected {
                    background: #23324B;
                    color: #E6EDF7;
                }
                QListWidget#effectsList::item {
                    background: #1E2A40;
                    color: #E6EDF7;
                    border: 1px solid #1E6CFF;
                    border-radius: 10px;
                }
                QListWidget#effectsList::item:selected {
                    background: #253452;
                    color: #E6EDF7;
                    border: 1px solid #1E6CFF;
                }
                QLineEdit, QComboBox, QDoubleSpinBox {
                    background: #202737;
                    border: 1px solid #2A3345;
                    border-radius: 10px;
                    padding: 6px 8px;
                }
                QPushButton {
                    background: #1E6CFF;
                    color: #FFFFFF;
                    border: none;
                    border-radius: 10px;
                    padding: 6px 12px;
                }
                QPushButton:hover {
                    background: #1A5EE0;
                }
                QPushButton:pressed {
                    background: #164FB8;
                }
                QScrollBar:vertical {
                    background: transparent;
                    width: 10px;
                    margin: 4px;
                }
                QScrollBar::handle:vertical {
                    background: #3A455E;
                    border-radius: 5px;
                    min-height: 20px;
                }
                QScrollBar:horizontal {
                    background: transparent;
                    height: 10px;
                    margin: 4px;
                }
                QScrollBar::handle:horizontal {
                    background: #3A455E;
                    border-radius: 5px;
                    min-width: 20px;
                }
                QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {
                    height: 0px;
                }
                QScrollBar::add-line:horizontal, QScrollBar::sub-line:horizontal {
                    width: 0px;
                }
                QMenu {
                    background: #1B2130;
                    border: 1px solid #2A3345;
                    border-radius: 10px;
                    padding: 6px;
                    color: #E6EDF7;
                }
                QMenu::item {
                    padding: 6px 10px;
                    border-radius: 8px;
                }
                QMenu::item:selected {
                    background: #243149;
                }
                QLabel#videoPreview {
                    background: #1B2130;
                    border: 1px solid #2A3345;
                    border-radius: 16px;
                }
                QSplitter::handle {
                    background: #2A3345;
                }
                QSplitter::handle:horizontal {
                    width: 6px;
                }
                QSplitter::handle:vertical {
                    height: 6px;
                }
                """
            )
        else:
            self.setStyleSheet(
                """
                QMainWindow {
                    background: #F5F7FB;
                    color: #1B1F2A;
                }
                QLabel, QToolButton, QTabBar::tab, QListWidget, QLineEdit, QComboBox, QDoubleSpinBox {
                    color: #1B1F2A;
                }
                QToolBar {
                    background: #FFFFFF;
                    border-bottom: 1px solid #E3E8F2;
                    spacing: 6px;
                    padding: 6px;
                }
                QToolButton {
                    background: transparent;
                    border-radius: 12px;
                    padding: 6px 10px;
                }
                QToolButton:hover {
                    background: #EEF3FF;
                }
                QToolButton:pressed {
                    background: #DEE8FF;
                }
                QToolButton:checked {
                    background: #E1EBFF;
                }
                QTabWidget::pane {
                    border: 1px solid #E3E8F2;
                    border-radius: 14px;
                    background: #FFFFFF;
                }
                QTabBar::tab {
                    background: #EEF2FB;
                    border-radius: 10px;
                    padding: 6px 12px;
                    margin: 4px;
                }
                QTabBar::tab:selected {
                    background: #FFFFFF;
                    border: 1px solid #D6E2FF;
                }
                QListWidget {
                    background: #FFFFFF;
                    border: 1px solid #E3E8F2;
                    border-radius: 12px;
                    padding: 6px;
                }
                QListWidget::item {
                    border-radius: 10px;
                    padding: 6px;
                }
                QListWidget::item:selected {
                    background: #EAF1FF;
                    color: #0B2559;
                }
                QListWidget#effectsList::item {
                    background: #EAF1FF;
                    color: #1B1F2A;
                    border: 1px solid #1E6CFF;
                    border-radius: 10px;
                }
                QListWidget#effectsList::item:selected {
                    background: #DCE8FF;
                    color: #1B1F2A;
                    border: 1px solid #1E6CFF;
                }
                QLineEdit, QComboBox, QDoubleSpinBox {
                    background: #F8FAFF;
                    border: 1px solid #E1E7F2;
                    border-radius: 10px;
                    padding: 6px 8px;
                }
                QPushButton {
                    background: #1E6CFF;
                    color: #FFFFFF;
                    border: none;
                    border-radius: 10px;
                    padding: 6px 12px;
                }
                QPushButton:hover {
                    background: #1A5EE0;
                }
                QPushButton:pressed {
                    background: #164FB8;
                }
                QScrollBar:vertical {
                    background: transparent;
                    width: 10px;
                    margin: 4px;
                }
                QScrollBar::handle:vertical {
                    background: #D2DBEF;
                    border-radius: 5px;
                    min-height: 20px;
                }
                QScrollBar:horizontal {
                    background: transparent;
                    height: 10px;
                    margin: 4px;
                }
                QScrollBar::handle:horizontal {
                    background: #D2DBEF;
                    border-radius: 5px;
                    min-width: 20px;
                }
                QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {
                    height: 0px;
                }
                QScrollBar::add-line:horizontal, QScrollBar::sub-line:horizontal {
                    width: 0px;
                }
                QMenu {
                    background: #FFFFFF;
                    border: 1px solid #E3E8F2;
                    border-radius: 10px;
                    padding: 6px;
                    color: #1B1F2A;
                }
                QMenu::item {
                    padding: 6px 10px;
                    border-radius: 8px;
                }
                QMenu::item:selected {
                    background: #EEF3FF;
                }
                QLabel#videoPreview {
                    background: #FFFFFF;
                    border: 1px solid #E3E8F2;
                    border-radius: 16px;
                }
                QSplitter::handle {
                    background: #E3E8F2;
                }
                QSplitter::handle:horizontal {
                    width: 6px;
                }
                QSplitter::handle:vertical {
                    height: 6px;
                }
                """
            )

        self.scene.set_theme(mode)
        self.timeline.set_theme(mode)

    def _toggle_theme_mode(self):
        self._theme_mode = "dark" if self.action_theme_toggle.isChecked() else "light"
        self._apply_theme(self._theme_mode)
        self._set_theme_icon()

    def _set_theme_icon(self):
        icon_name = "moon.png" if self._theme_mode == "light" else "sun.png"
        self._set_action_icon(self.action_theme_toggle, icon_name)

    def _apply_dialog_theme(self, dlg: QtWidgets.QDialog):
        if self._theme_mode == "dark":
            dlg.setStyleSheet(
                """
                QDialog { background: #1B2130; color: #E6EDF7; }
                QLabel { color: #E6EDF7; }
                QComboBox {
                    background: #202737;
                    border: 1px solid #2A3345;
                    border-radius: 8px;
                    padding: 4px 6px;
                    color: #E6EDF7;
                }
                QDialogButtonBox QPushButton {
                    background: #1E6CFF;
                    color: #FFFFFF;
                    border: none;
                    border-radius: 8px;
                    padding: 6px 10px;
                }
                """
            )
        else:
            dlg.setStyleSheet(
                """
                QDialog { background: #FFFFFF; color: #1B1F2A; }
                QLabel { color: #1B1F2A; }
                QComboBox {
                    background: #F8FAFF;
                    border: 1px solid #E1E7F2;
                    border-radius: 8px;
                    padding: 4px 6px;
                    color: #1B1F2A;
                }
                QDialogButtonBox QPushButton {
                    background: #1E6CFF;
                    color: #FFFFFF;
                    border: none;
                    border-radius: 8px;
                    padding: 6px 10px;
                }
                """
            )

    def _setup_window_effects(self):
        shadow = QtWidgets.QGraphicsDropShadowEffect(self.video_widget)
        shadow.setBlurRadius(24)
        shadow.setColor(QtGui.QColor(30, 60, 110, 40))
        shadow.setOffset(0, 6)
        self.video_widget.setGraphicsEffect(shadow)

        self._did_fade_in = False

    def showEvent(self, event: QtGui.QShowEvent):
        super().showEvent(event)
        self.setWindowOpacity(1.0)
