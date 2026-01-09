from PySide6 import QtWidgets


class RenderSettingsDialog(QtWidgets.QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Render Settings")
        self.setModal(True)
        self.resize(400, 300)

        layout = QtWidgets.QFormLayout(self)

                   
        self.combo_resolution = QtWidgets.QComboBox()
        self.combo_resolution.addItems(["Auto", "720p", "1080p", "1440p", "4K"])
        layout.addRow("Resolution:", self.combo_resolution)

                   
        self.combo_fps = QtWidgets.QComboBox()
        self.combo_fps.addItems(["Auto", "24", "30", "60"])
        layout.addRow("Framerate:", self.combo_fps)

               
        self.combo_codec = QtWidgets.QComboBox()
        self.combo_codec.addItems(["libx264 (H.264)", "libx265 (HEVC)", "prores", "vp9"])
        layout.addRow("Codec:", self.combo_codec)

                
        self.combo_preset = QtWidgets.QComboBox()
        self.combo_preset.addItems(["ultrafast", "superfast", "fast", "medium", "slow"])
        self.combo_preset.setCurrentText("medium")
        layout.addRow("Preset:", self.combo_preset)

                       
        self.combo_audio = QtWidgets.QComboBox()
        self.combo_audio.addItems(["128k", "192k", "256k", "320k"])
        self.combo_audio.setCurrentText("192k")
        layout.addRow("Audio bitrate:", self.combo_audio)

                 
        btns = QtWidgets.QDialogButtonBox.Ok | QtWidgets.QDialogButtonBox.Cancel
        self.buttonBox = QtWidgets.QDialogButtonBox(btns)
        self.buttonBox.accepted.connect(self.accept)
        self.buttonBox.rejected.connect(self.reject)
        layout.addRow(self.buttonBox)

    def get_settings(self) -> dict:
        return {
            "resolution": self.combo_resolution.currentText(),
            "fps": self.combo_fps.currentText(),
            "codec": self.combo_codec.currentText(),
            "preset": self.combo_preset.currentText(),
            "audio_bitrate": self.combo_audio.currentText(),
        }
