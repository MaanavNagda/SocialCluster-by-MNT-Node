"""Ctrl+Shift+U unicode codepoint entry (IBus-style).

Two layers covering every text field in the app:

- ``UNICODE_INPUT_JS`` is injected into every page/frame of the shared
  QWebEngineProfile so web-app fields (contenteditable composers like
  WhatsApp/Discord, plus inputs and textareas) get the shortcut natively.
- ``UnicodeLineEditFilter`` is a per-widget event filter that gives the
  same shortcut to the app's own native QLineEdit fields.

Both use the same interaction: Ctrl+Shift+U starts capture, up to 6 hex
digits are typed (shown in a floating "u<hex>" indicator), Enter or Space
inserts the character, Escape cancels, and any other key cancels and is
passed through normally.
"""

from PySide6.QtCore import QEvent, QObject, Qt, QTimer
from PySide6.QtWidgets import QLabel, QLineEdit

MAX_DIGITS = 6
_HEX_DIGITS = frozenset("0123456789abcdefABCDEF")

# Qt.KeypadModifier (0x20000000) is OR'd into event.key() for numpad keys;
# strip it so numpad digits map to hex like the top-row number row does.
_KEYPAD_MODIFIER = Qt.KeypadModifier.value


def hex_to_char(digits):
    """Return the unicode character for a 1-6 digit hex string, or None.

    Rejects empty input, non-hex characters, surrogate code points and
    values above U+10FFFF.
    """
    if not digits or len(digits) > MAX_DIGITS:
        return None
    if any(c not in _HEX_DIGITS for c in digits):
        return None
    cp = int(digits, 16)
    if cp > 0x10FFFF or 0xD800 <= cp <= 0xDFFF:
        return None
    try:
        return chr(cp)
    except (ValueError, OverflowError):
        return None


UNICODE_INPUT_JS = r"""
(function() {
    if (window.__scUnicodeInputInit) {
        return;
    }
    window.__scUnicodeInputInit = true;

    var MAX_DIGITS = 6;
    var session = null;  // {digits: string, ui: {host, inner}} while capturing

    function focusedEditable() {
        var el = document.activeElement;
        var guard = 0;
        while (el && el.shadowRoot && el.shadowRoot.activeElement && guard++ < 10) {
            el = el.shadowRoot.activeElement;
        }
        if (!el || el === document.body || el === document.documentElement) {
            return null;
        }
        if (el.isContentEditable) {
            return el;
        }
        if (el.tagName === 'TEXTAREA') {
            return (!el.readOnly && !el.disabled) ? el : null;
        }
        if (el.tagName === 'INPUT') {
            if (el.readOnly || el.disabled) {
                return null;
            }
            var type = (el.getAttribute('type') || 'text').toLowerCase();
            var textTypes = {
                'text': 1, 'search': 1, 'url': 1, 'tel': 1,
                'password': 1, 'email': 1, 'number': 1
            };
            return textTypes[type] ? el : null;
        }
        return null;
    }

    function hexCharFor(e) {
        if (/^[0-9a-fA-F]$/.test(e.key)) {
            return e.key.toLowerCase();
        }
        // Physical-key fallbacks so digits typed while Shift is still held
        // (e.g. Shift+1 -> '!') and numpad keys still register.
        var m = /^(?:Digit|Numpad)([0-9])$/.exec(e.code || '');
        if (m) {
            return m[1];
        }
        m = /^Key([a-fA-F])$/.exec(e.code || '');
        if (m) {
            return m[1].toLowerCase();
        }
        return null;
    }

    function charForDigits(digits) {
        if (!digits) {
            return null;
        }
        var cp = parseInt(digits, 16);
        if (isNaN(cp) || cp > 0x10FFFF || (cp >= 0xD800 && cp <= 0xDFFF)) {
            return null;
        }
        try {
            return String.fromCodePoint(cp);
        } catch (err) {
            return null;
        }
    }

    function createIndicator() {
        var host = document.createElement('div');
        host.style.cssText =
            'position:fixed;left:0;top:0;z-index:2147483647;' +
            'pointer-events:none;';
        // Shadow DOM so page stylesheets can't restyle the indicator.
        var root = host.attachShadow({mode: 'open'});
        var inner = document.createElement('span');
        inner.style.cssText =
            'display:inline-block;background:rgba(25,25,25,0.95);color:#fff;' +
            'font:13px/1.5 monospace;padding:3px 9px;border-radius:4px;' +
            'text-decoration:underline;white-space:pre;';
        root.appendChild(inner);
        (document.documentElement || document.body).appendChild(host);
        return {host: host, inner: inner};
    }

    function caretRect() {
        try {
            var sel = window.getSelection();
            if (sel && sel.rangeCount > 0) {
                var r = sel.getRangeAt(0).getBoundingClientRect();
                if (r && (r.width || r.height || r.top || r.bottom)) {
                    return r;
                }
            }
        } catch (e) {}
        return null;
    }

    function positionIndicator(ui) {
        var rect = caretRect();
        if (!rect) {
            var el = focusedEditable();
            if (el) {
                rect = el.getBoundingClientRect();
            }
        }
        var x, y;
        if (rect && (rect.width || rect.height || rect.top || rect.bottom)) {
            x = rect.left + 4;
            y = rect.bottom + 4;
        } else {
            x = window.innerWidth / 2;
            y = window.innerHeight - 48;
        }
        var w = ui.host.offsetWidth || 80;
        var h = ui.host.offsetHeight || 24;
        x = Math.max(4, Math.min(x, window.innerWidth - w - 4));
        y = Math.max(4, Math.min(y, window.innerHeight - h - 4));
        ui.host.style.left = x + 'px';
        ui.host.style.top = y + 'px';
    }

    function updateIndicator() {
        var label = 'u' + session.digits;
        var ch = charForDigits(session.digits);
        if (ch) {
            label += ' ' + ch;
        }
        session.ui.inner.textContent = label;
        positionIndicator(session.ui);
    }

    function startSession() {
        session = {digits: '', ui: createIndicator()};
        updateIndicator();
    }

    function endSession() {
        if (!session) {
            return;
        }
        var host = session.ui.host;
        session = null;
        if (host.parentNode) {
            host.parentNode.removeChild(host);
        }
    }

    function failSession() {
        if (!session) {
            return;
        }
        var ui = session.ui;
        session = null;
        ui.inner.style.background = '#c0392b';
        setTimeout(function() {
            if (ui.host.parentNode) {
                ui.host.parentNode.removeChild(ui.host);
            }
        }, 250);
    }

    function insertInto(el, ch) {
        if (el.tagName === 'INPUT' || el.tagName === 'TEXTAREA') {
            // execCommand('insertText') does not reach input/textarea, so
            // splice the value at the caret and fire a real input event so
            // frameworks (React etc.) see the change.
            try {
                if (el.selectionStart === null || el.selectionStart === undefined) {
                    el.value += ch;
                } else {
                    el.setRangeText(ch, el.selectionStart, el.selectionEnd, 'end');
                }
            } catch (err) {
                el.value += ch;
            }
            el.dispatchEvent(new Event('input', {bubbles: true}));
            return;
        }
        // contenteditable: execCommand goes through Chromium's real input
        // pipeline (beforeinput/input events + undo), which editors like
        // WhatsApp and Discord require.
        if (document.execCommand('insertText', false, ch)) {
            return;
        }
        // Fallback (e.g. editable inside a shadow root where execCommand on
        // the document can't reach the shadow selection).
        var root = el.getRootNode ? el.getRootNode() : document;
        var sel = (root && root.getSelection) ? root.getSelection() : window.getSelection();
        if (!sel || sel.rangeCount === 0) {
            return;
        }
        var range = sel.getRangeAt(0);
        range.deleteContents();
        var node = document.createTextNode(ch);
        range.insertNode(node);
        range.setStartAfter(node);
        range.collapse(true);
        sel.removeAllRanges();
        sel.addRange(range);
        el.dispatchEvent(new InputEvent('input', {
            bubbles: true,
            data: ch,
            inputType: 'insertText'
        }));
    }

    function commitSession() {
        var digits = session ? session.digits : '';
        if (!digits) {
            endSession();
            return;
        }
        var ch = charForDigits(digits);
        if (ch === null) {
            failSession();
            return;
        }
        var el = focusedEditable();
        endSession();
        if (!el) {
            return;
        }
        el.focus();
        insertInto(el, ch);
    }

    function onKeyDown(e) {
        if (window.__scUnicodeEnabled === false) {
            if (session) {
                endSession();
            }
            return;
        }
        var k = e.key;
        if (session) {
            // Re-pressing the trigger inside a session is ignored.
            if (e.ctrlKey && e.shiftKey && !e.altKey && !e.metaKey &&
                    (e.code === 'KeyU' || k === 'u' || k === 'U')) {
                e.preventDefault();
                e.stopImmediatePropagation();
                return;
            }
            // Ctrl/Alt/Meta combos (copy, paste, ...) cancel the session
            // and pass through untouched, like the system IME does.
            if (e.ctrlKey || e.altKey || e.metaKey) {
                endSession();
                return;
            }
            if (k === 'Escape') {
                e.preventDefault();
                e.stopImmediatePropagation();
                endSession();
                return;
            }
            if (k === 'Enter' || k === ' ' || k === 'Spacebar') {
                e.preventDefault();
                e.stopImmediatePropagation();
                commitSession();
                return;
            }
            if (k === 'Backspace') {
                e.preventDefault();
                e.stopImmediatePropagation();
                session.digits = session.digits.slice(0, -1);
                updateIndicator();
                return;
            }
            var hex = hexCharFor(e);
            if (hex && session.digits.length < MAX_DIGITS) {
                e.preventDefault();
                e.stopImmediatePropagation();
                session.digits += hex;
                updateIndicator();
                return;
            }
            endSession();
            return;
        }
        var isU = e.code === 'KeyU' || k === 'u' || k === 'U';
        if (e.ctrlKey && e.shiftKey && !e.altKey && !e.metaKey && isU) {
            if (!focusedEditable()) {
                return;
            }
            e.preventDefault();
            e.stopImmediatePropagation();
            startSession();
        }
    }

    window.addEventListener('keydown', onKeyDown, true);
    window.addEventListener('mousedown', function() {
        if (session) {
            endSession();
        }
    }, true);
    window.addEventListener('blur', function() {
        if (session) {
            endSession();
        }
    }, true);
    window.addEventListener('scroll', function() {
        if (session) {
            positionIndicator(session.ui);
        }
    }, true);
})();
"""


class UnicodeLineEditFilter(QObject):
    """Event filter adding IBus-style Ctrl+Shift+U entry to a QLineEdit.

    While a capture session is active on a QLineEdit, hex digits are
    swallowed, a small "u<hex>" indicator is overlaid on the widget, and
    Enter/Space inserts the character at the cursor. Escape cancels; any
    other key cancels and passes through.

    One instance can be shared by any number of widgets; attach it with
    install_on(). It must NOT be installed on QApplication: app-level
    filters run for every event on every QObject, including Qt-internal
    C++-created objects (e.g. QtWebEngine's delegate widgets), and PySide6
    can segfault wrapping those objects when dispatching to a Python
    filter (getWrapperForQObject).
    """

    def __init__(self, config, theme, parent=None):
        super().__init__(parent)
        self._config = config
        self._theme = theme
        self._target = None
        self._label = None
        self._digits = ""

    def install_on(self, widget):
        """Attach this filter to a QLineEdit (see class docstring)."""
        widget.installEventFilter(self)

    def set_theme(self, theme):
        self._theme = theme
        if self._label is not None:
            self._label.setStyleSheet(self._label_style())

    # -- eventFilter ---------------------------------------------------- #

    def eventFilter(self, obj, event):
        etype = event.type()
        if etype == QEvent.KeyPress:
            return self._on_key_press(obj, event)
        if self._target is not None and obj == self._target:
            if etype in (QEvent.FocusOut, QEvent.Hide):
                self._cancel()
            elif etype == QEvent.Resize:
                self._position_label()
        return False

    def _on_key_press(self, obj, event):
        if self._target is not None:
            if obj != self._target:
                # Keys heading to another widget mean focus moved without a
                # FocusOut reaching us (e.g. popup grabs); end the session.
                self._cancel()
                return False
            return self._handle_pending_key(self._target, event)
        if not isinstance(obj, QLineEdit) or obj.isReadOnly():
            return False
        if not self._config.get("unicode_input", True):
            return False
        if event.key() == Qt.Key_U and event.modifiers() == (
            Qt.ControlModifier | Qt.ShiftModifier
        ):
            self._begin(obj)
            return True
        return False

    def _handle_pending_key(self, widget, event):
        key = event.key()
        mods = event.modifiers()
        if key == Qt.Key_U and mods == (Qt.ControlModifier | Qt.ShiftModifier):
            return True
        if mods & (Qt.ControlModifier | Qt.AltModifier | Qt.MetaModifier):
            self._cancel()
            return False
        if key == Qt.Key_Escape:
            self._cancel()
            return True
        if key in (Qt.Key_Return, Qt.Key_Enter, Qt.Key_Space):
            self._commit(widget)
            return True
        if key == Qt.Key_Backspace:
            self._digits = self._digits[:-1]
            self._update_label()
            return True
        ch = self._event_hex_char(event)
        if ch is not None and len(self._digits) < MAX_DIGITS:
            self._digits += ch
            self._update_label()
            return True
        self._cancel()
        return False

    @staticmethod
    def _event_hex_char(event):
        text = event.text()
        if len(text) == 1 and text in _HEX_DIGITS:
            return text.lower()
        base = event.key() & ~_KEYPAD_MODIFIER
        if Qt.Key_0 <= base <= Qt.Key_9:
            return chr(base)
        if Qt.Key_A <= base <= Qt.Key_F:
            return chr(base).lower()
        return None

    # -- session lifecycle ---------------------------------------------- #

    def _begin(self, widget):
        self._cancel()
        self._target = widget
        self._digits = ""
        label = QLabel("u", widget)
        label.setStyleSheet(self._label_style())
        label.setAttribute(Qt.WA_TransparentForMouseEvents)
        label.setFocusPolicy(Qt.NoFocus)
        label.adjustSize()
        self._label = label
        self._position_label()
        label.show()
        widget.destroyed.connect(self._on_target_destroyed)

    def _cancel(self, *args):
        target = self._target
        label = self._label
        self._target = None
        self._label = None
        self._digits = ""
        if target is not None:
            try:
                target.destroyed.disconnect(self._on_target_destroyed)
            except (RuntimeError, TypeError):
                pass
        if label is not None:
            try:
                label.deleteLater()
            except RuntimeError:
                pass

    def _fail(self):
        label = self._label
        self._target = None
        self._label = None
        self._digits = ""
        if label is None:
            return
        label.setStyleSheet(
            "QLabel { background-color: #c0392b; color: #ffffff; "
            "border-radius: 4px; padding: 1px 6px; font-family: monospace; }"
        )
        QTimer.singleShot(250, lambda l=label: l.deleteLater())

    def _commit(self, widget):
        ch = hex_to_char(self._digits)
        if self._digits and ch is None:
            self._fail()
            return
        self._cancel()
        if ch is not None:
            widget.insert(ch)

    def _on_target_destroyed(self, obj=None):
        # Only clear if the *current* target died -- a stale connection on
        # a previously used widget must not kill a newer session.
        if self._target is not None and obj == self._target:
            self._target = None
            self._label = None  # label is a child of the widget, dead too
            self._digits = ""

    # -- indicator ------------------------------------------------------ #

    def _label_style(self):
        return (
            "QLabel {"
            f"background-color: {self._theme['panel']};"
            f"color: {self._theme['fg']};"
            f"border: 1px solid {self._theme['primary']};"
            "border-radius: 4px;"
            "padding: 1px 6px;"
            "font-family: monospace;"
            "text-decoration: underline;"
            "}"
        )

    def _update_label(self):
        if self._label is None:
            return
        text = "u" + self._digits
        ch = hex_to_char(self._digits)
        if ch is not None:
            text += " " + ch
        self._label.setText(text)
        self._position_label()

    def _position_label(self):
        if self._label is None or self._target is None:
            return
        self._label.adjustSize()
        x = max(2, self._target.width() - self._label.width() - 6)
        y = max(0, (self._target.height() - self._label.height()) // 2)
        self._label.move(x, y)
