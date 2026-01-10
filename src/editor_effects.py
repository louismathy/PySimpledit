from typing import Optional

from PySide6 import QtWidgets
from PySide6.QtCore import Qt

from models import ClipItem


AVAILABLE_EFFECTS = {
    "bw": "Black & White",
    "invert": "Invert Colors",
    "sepia": "Sepia Tone",
    "brightness": "Brightness",
    "contrast": "Contrast",
    "mirror": "Mirror (Horizontal Flip)",
}

REVERSE_AVAILABLE_EFFECTS = {v: k for k, v in AVAILABLE_EFFECTS.items()}


class EditorEffectsMixin:
    def _current_clip_or_none(self) -> Optional[ClipItem]:
        return self.current_clip()

    def _refresh_effects_ui(self):
        c = self._current_clip_or_none()
        self.list_effects.clear()
        if not c:
            self._update_effect_buttons_enabled()
            return

        for ec in (c.effects or []):
            t = ec.get("type", "")
            label = AVAILABLE_EFFECTS.get(t, f"Unknown ({t})")
            item = QtWidgets.QListWidgetItem(label)
            item.setData(Qt.UserRole, ec)
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
        c = self._clip_at_time(self.current_time)
        if c:
            local = c.trim_in + (self.current_time - c.start_time)
            self._request_frame(c.path, local)

    def on_effect_add(self):
        c = self._current_clip_or_none()
        if not c:
            return
        eff_label = self.combo_eff_add.currentText().strip()
        eff_key = REVERSE_AVAILABLE_EFFECTS.get(eff_label)
        if not eff_key:
            return
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
