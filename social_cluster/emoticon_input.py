"""Typed emoticon-to-emoji conversion for native Qt line edits."""

from PySide6.QtCore import QEvent, QObject, Qt, QTimer
from PySide6.QtWidgets import QLineEdit

from social_cluster.emoticons import (
    find_emoticon_replacement,
    python_index_for_utf16_offset,
    utf16_offset_for_python_index,
)


class EmoticonLineEditConverter(QObject):
    """Convert typed emoticons in QLineEdit widgets when enabled in config."""

    def __init__(self, config, parent=None):
        super().__init__(parent)
        self._config = config

    def install_on(self, widget):
        """Attach conversion to a QLineEdit."""
        if not isinstance(widget, QLineEdit):
            raise TypeError("EmoticonLineEditConverter only supports QLineEdit")
        widget.installEventFilter(self)

    def eventFilter(self, obj, event):
        if event.type() != QEvent.KeyPress:
            return False
        if not isinstance(obj, QLineEdit):
            return False
        if not self._config.get("emoticons_to_emoji", False):
            return False
        if obj.isReadOnly() or obj.echoMode() != QLineEdit.Normal:
            return False
        if event.modifiers() & (Qt.ControlModifier | Qt.AltModifier | Qt.MetaModifier):
            return False
        if len(event.text()) != 1 or not event.text().isprintable():
            return False

        # Let QLineEdit insert the typed character first, then perform the
        # replacement. Besides matching the web-input behavior, keeping the
        # final typed character in Qt's undo history lets one undo restore
        # the original emoticon instead of only its prefix.
        QTimer.singleShot(0, obj, lambda w=obj: self._convert(w))
        return False

    def _convert(self, widget):
        if not self._config.get("emoticons_to_emoji", False):
            return
        if widget.isReadOnly() or widget.echoMode() != QLineEdit.Normal:
            return

        text = widget.text()
        cursor_position = python_index_for_utf16_offset(text, widget.cursorPosition())
        if cursor_position is None:
            return
        replacement = find_emoticon_replacement(text, cursor_position)
        if replacement is None:
            return

        start, end, _emoticon, emoji = replacement
        qt_start = utf16_offset_for_python_index(text, start)
        qt_end = utf16_offset_for_python_index(text, end)
        if qt_start is None or qt_end is None:
            return

        widget.setSelection(qt_start, qt_end - qt_start)
        widget.insert(emoji)
