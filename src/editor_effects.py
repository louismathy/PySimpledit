import os
from typing import Optional

from PySide6 import QtWidgets, QtCore, QtGui
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

class EditorEffectsMixin:
    def _current_clip_or_none(self) -> Optional[ClipItem]:
        return self.current_clip()

    def _refresh_effects_ui(self):
        c = self._current_clip_or_none()
        self.list_effects.clear()
        if not c:
            self._update_effect_buttons_enabled()
            self._refresh_effects_browser()
            return

        for ec in (c.effects or []):
            t = ec.get("type", "")
            label = AVAILABLE_EFFECTS.get(t, f"Unknown ({t})")
            item = QtWidgets.QListWidgetItem(label)
            item.setData(Qt.UserRole, ec)
            item.setSizeHint(QtCore.QSize(0, 32))
            self.list_effects.addItem(item)

        self._update_effect_buttons_enabled()
        self._refresh_effects_browser()

    def _update_effect_buttons_enabled(self):
        has_sel = len(self.list_effects.selectedIndexes()) == 1
        self.btn_eff_remove.setEnabled(has_sel)
        self.btn_eff_up.setEnabled(has_sel and self.list_effects.currentRow() > 0)
        self.btn_eff_down.setEnabled(
            has_sel and 0 <= self.list_effects.currentRow() < (self.list_effects.count() - 1)
        )
        if hasattr(self, "list_effects_browser"):
            has_browser_sel = len(self.list_effects_browser.selectedIndexes()) == 1
            has_clip = self._current_clip_or_none() is not None
            self.btn_eff_add.setEnabled(has_browser_sel and has_clip)

    def _apply_effects_preview_refresh(self):
        c = self._clip_at_time(self.current_time)
        if c:
            local = c.trim_in + (self.current_time - c.start_time)
            self._request_frame(c.path, local)

    def on_effect_add_from_browser(self):
        c = self._current_clip_or_none()
        if not c:
            return
        if not hasattr(self, "list_effects_browser"):
            return
        item = self.list_effects_browser.currentItem()
        if not item:
            return
        eff_key = item.data(Qt.UserRole)
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

    def _on_effect_item_clicked(self, item: QtWidgets.QListWidgetItem):
        cfg = item.data(Qt.UserRole)
        if not cfg:
            return
        self._show_effect_preview(cfg, item)

    def _show_effect_preview(self, cfg: dict, item: QtWidgets.QListWidgetItem):
        row = self.list_effects.row(item)
        if row >= 0:
            self.list_effects.setCurrentRow(row)
        from effects import apply_chain_qimage

        base_img = self._current_preview_image()
        if base_img is None:
            base_img = self._placeholder_preview_image()

        try:
            img = apply_chain_qimage(base_img, [cfg])
        except Exception:
            img = base_img

        pix = QtGui.QPixmap.fromImage(img)
        pix = pix.scaled(220, 124, QtCore.Qt.KeepAspectRatio, QtCore.Qt.SmoothTransformation)

        menu = QtWidgets.QMenu(self.list_effects)
        menu.setFont(QtGui.QFont("SF Pro Display", 9))
        action = QtWidgets.QWidgetAction(menu)
        label = QtWidgets.QLabel()
        label.setPixmap(pix)
        label.setFixedSize(pix.size())
        action.setDefaultWidget(label)
        menu.addAction(action)
        rect = self.list_effects.visualItemRect(item)
        anchor = self.list_effects.viewport().mapToGlobal(rect.bottomLeft())
        menu.popup(anchor)

    def _effects_browser_target_size(self) -> QtCore.QSize:
        if hasattr(self, "list_effects_browser"):
            size = self.list_effects_browser.iconSize()
            if size.isValid() and size.width() > 0 and size.height() > 0:
                return size
        return QtCore.QSize(160, 90)

    def _refresh_effects_browser(self):
        if not hasattr(self, "list_effects_browser"):
            return
        from effects import apply_chain_qimage

        current_key = None
        current_item = self.list_effects_browser.currentItem()
        if current_item:
            current_key = current_item.data(Qt.UserRole)

        if self._current_clip_or_none() is None:
            base_img = self._placeholder_preview_image()
        else:
            base_img = self._current_preview_image()
            if base_img is None:
                base_img = self._placeholder_preview_image()

        target = self._effects_browser_target_size()
        self.list_effects_browser.clear()
        for eff_key, label in AVAILABLE_EFFECTS.items():
            cfg = {"type": eff_key, "params": {}}
            try:
                img = apply_chain_qimage(base_img, [cfg])
            except Exception:
                img = base_img
            img = self._scale_and_crop_qimage(img, target)
            pix = QtGui.QPixmap.fromImage(img)
            item = QtWidgets.QListWidgetItem(label)
            item.setData(Qt.UserRole, eff_key)
            item.setIcon(QtGui.QIcon(pix))
            item.setToolTip(label)
            self.list_effects_browser.addItem(item)

        if current_key:
            for i in range(self.list_effects_browser.count()):
                item = self.list_effects_browser.item(i)
                if item.data(Qt.UserRole) == current_key:
                    self.list_effects_browser.setCurrentItem(item)
                    break

    def _maybe_refresh_effects_browser(self):
        if not hasattr(self, "list_effects_browser"):
            return
        interval = 0 if not getattr(self, "playing", False) else 400
        now_ms = QtCore.QTime.currentTime().msecsSinceStartOfDay()
        last_ms = getattr(self, "_effects_preview_last_ms", -9999)
        if interval and now_ms - last_ms < interval:
            return
        self._effects_preview_last_ms = now_ms
        self._refresh_effects_browser()

    def _scale_and_crop_qimage(self, img: QtGui.QImage, target: QtCore.QSize) -> QtGui.QImage:
        if img.isNull():
            return img
        scaled = img.scaled(target, QtCore.Qt.KeepAspectRatioByExpanding, QtCore.Qt.SmoothTransformation)
        x = max(0, (scaled.width() - target.width()) // 2)
        y = max(0, (scaled.height() - target.height()) // 2)
        return scaled.copy(x, y, target.width(), target.height())

    def _current_preview_image(self) -> QtGui.QImage | None:
        if hasattr(self, "_last_preview_qimg"):
            img = getattr(self, "_last_preview_qimg")
            if isinstance(img, QtGui.QImage) and not img.isNull():
                return img
        if isinstance(self.video_widget, QtWidgets.QLabel):
            pix = self.video_widget.pixmap()
            if pix is not None:
                return pix.toImage()
        return None

    def _placeholder_preview_image(self) -> QtGui.QImage:
        asset_path = os.path.join(os.path.dirname(__file__), "assets", "preview", "effect_preview.jpg")
        img = QtGui.QImage(asset_path)
        if not img.isNull():
            return img
        w = max(220, self.video_widget.width())
        h = max(124, self.video_widget.height())
        img = QtGui.QImage(w, h, QtGui.QImage.Format_RGB32)
        img.fill(QtGui.QColor(244, 247, 251))
        p = QtGui.QPainter(img)
        p.setPen(QtGui.QColor(140, 150, 168))
        p.setFont(QtGui.QFont("SF Pro Display", 10))
        p.drawText(img.rect(), QtCore.Qt.AlignCenter, "No preview")
        p.end()
        return img
