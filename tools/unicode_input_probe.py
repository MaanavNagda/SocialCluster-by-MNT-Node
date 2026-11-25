#!/usr/bin/env python3
"""Verify unicode input and emoticon conversion inside Qt WebEngine pages.

Simulates the real key path: injects social_cluster's UNICODE_INPUT_JS into a
profile (same as social_cluster.main does), loads a page with a
contenteditable div and an <input>, focuses each, sends raw key events to the
web view's focus proxy, and checks that the expected characters landed in the
DOM.

Usage:  python3 tools/unicode_input_probe.py

Exits 0 and prints "ok" if all insertions work, otherwise prints "missing"
plus details and exits 1.
"""

import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

HTML = (
    "<html><body>"
    "<div id='ed' contenteditable='true' style='width:300px;height:60px'></div>"
    "<input id='inp'>"
    "<textarea id='ta'></textarea>"
    "<input id='pw' type='password'>"
    "<iframe id='fr' srcdoc=\"<input id='frameinp'>\"></iframe>"
    "</body></html>"
)


def probe():
    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
    os.environ.setdefault(
        "QTWEBENGINE_CHROMIUM_FLAGS", "--disable-gpu --no-sandbox"
    )
    try:
        from PySide6.QtCore import QEvent, QEventLoop, Qt, QTimer
        from PySide6.QtGui import QKeyEvent
        from PySide6.QtWidgets import QApplication
        from PySide6.QtWebEngineCore import (
            QWebEnginePage,
            QWebEngineProfile,
            QWebEngineScript,
        )
        from PySide6.QtWebEngineWidgets import QWebEngineView
    except ImportError:
        return None

    from social_cluster.main import run_js_in_all_frames
    from social_cluster.unicode_input import UNICODE_INPUT_JS, input_flags_js

    app = QApplication(sys.argv)

    profile = QWebEngineProfile("unicode-input-probe", app)
    script = QWebEngineScript()
    script.setName("unicode-input")
    script.setSourceCode(UNICODE_INPUT_JS)
    script.setInjectionPoint(QWebEngineScript.DocumentCreation)
    script.setWorldId(QWebEngineScript.MainWorld)
    script.setRunsOnSubFrames(True)
    profile.scripts().insert(script)

    view = QWebEngineView()
    view.setPage(QWebEnginePage(profile, view))
    view.resize(640, 480)
    view.show()

    loop = QEventLoop()
    view.page().loadFinished.connect(loop.quit)
    QTimer.singleShot(20000, loop.quit)
    view.setHtml(HTML)
    loop.exec()

    def js(expr):
        out = {}
        inner = QEventLoop()
        view.page().runJavaScript(
            expr, lambda r: (out.setdefault("r", r), inner.quit())
        )
        QTimer.singleShot(5000, inner.quit)
        inner.exec()
        return out.get("r")

    def send(key, mods=Qt.NoModifier, text=""):
        target = view.focusProxy() or view
        QApplication.sendEvent(target, QKeyEvent(QEvent.KeyPress, key, mods, text))
        app.processEvents()

    def type_text(chars):
        for c in chars:
            send(ord(c.upper()), Qt.NoModifier, c)

    def settle():
        inner = QEventLoop()
        QTimer.singleShot(400, inner.quit)
        inner.exec()

    results = {}

    js("document.getElementById('ed').focus()")
    (view.focusProxy() or view).setFocus()
    app.processEvents()
    send(Qt.Key_U, Qt.ControlModifier | Qt.ShiftModifier, "U")
    type_text("1f600")
    send(Qt.Key_Return, Qt.NoModifier, "\r")
    settle()
    results["contenteditable"] = js("document.getElementById('ed').textContent")

    js("document.getElementById('inp').focus()")
    app.processEvents()
    send(Qt.Key_U, Qt.ControlModifier | Qt.ShiftModifier, "U")
    type_text("e9")
    send(Qt.Key_Return, Qt.NoModifier, "\r")
    settle()
    results["input"] = js("document.getElementById('inp').value")

    js("document.getElementById('ed').focus()")
    app.processEvents()
    send(Qt.Key_U, Qt.ControlModifier | Qt.ShiftModifier, "U")
    type_text("41")
    send(Qt.Key_Escape, Qt.NoModifier, "")
    send(Qt.Key_Return, Qt.NoModifier, "\r")
    settle()
    results["escape"] = js("document.getElementById('ed').textContent")

    js(
        "window.__scEmoticonsEnabled = false;"
        "(function(){var i=document.getElementById('inp');i.value='';i.focus();})()"
    )
    app.processEvents()
    type_text(":)")
    settle()
    results["emoticon_input_disabled"] = js("document.getElementById('inp').value")

    js(
        "window.__scEmoticonsEnabled = true;"
        "(function(){var i=document.getElementById('inp');i.value='';i.focus();})()"
    )
    app.processEvents()
    type_text(":)")
    settle()
    results["emoticon_input"] = js("document.getElementById('inp').value")

    js(
        "window.__scEmoticonsEnabled = true;"
        "(function(){var i=document.getElementById('inp');i.value='😀';"
        "i.focus();i.setSelectionRange(i.value.length,i.value.length);})()"
    )
    app.processEvents()
    type_text(":)")
    settle()
    results["emoticon_input_after_emoji"] = js("document.getElementById('inp').value")

    js(
        "window.__scEmoticonsEnabled = true;"
        "(function(){var i=document.getElementById('inp');i.value='';i.focus();})()"
    )
    app.processEvents()
    type_text("https://")
    settle()
    results["emoticon_input_url"] = js("document.getElementById('inp').value")

    js(
        "window.__scEmoticonsEnabled = true;"
        "(function(){var ta=document.getElementById('ta');ta.value='';ta.focus();})()"
    )
    app.processEvents()
    type_text(":)")
    settle()
    results["emoticon_textarea"] = js("document.getElementById('ta').value")

    js(
        "window.__scEmoticonsEnabled = true;"
        "(function(){var pw=document.getElementById('pw');pw.value='';pw.focus();})()"
    )
    app.processEvents()
    type_text(":)")
    settle()
    results["emoticon_password"] = js("document.getElementById('pw').value")

    js(
        "window.__scEmoticonsEnabled = true;"
        "(function(){var ed=document.getElementById('ed');ed.textContent='';ed.focus();})()"
    )
    app.processEvents()
    type_text(":)")
    settle()
    results["emoticon_contenteditable"] = js("document.getElementById('ed').textContent")

    js(
        "window.__scEmoticonsEnabled = true;"
        "(function(){var ed=document.getElementById('ed');ed.textContent='';ed.focus();})()"
    )
    app.processEvents()
    type_text(":-)")
    settle()
    results["emoticon_contenteditable_long"] = js("document.getElementById('ed').textContent")

    run_js_in_all_frames(
        view.page(),
        input_flags_js({"unicode_input": True, "emoticons_to_emoji": True}),
    )
    settle()
    js(
        "(function(){var frame=document.getElementById('fr');"
        "var i=frame.contentDocument.getElementById('frameinp');"
        "i.value='';i.focus();})()"
    )
    app.processEvents()
    type_text(":)")
    settle()
    results["emoticon_iframe_input"] = js(
        "document.getElementById('fr')"
        ".contentDocument.getElementById('frameinp').value"
    )

    return results


def main():
    results = probe()
    failures = {
        "contenteditable": results and results.get("contenteditable") != "\U0001F600",
        "input": results and results.get("input") != "\u00e9",
        "escape": results and results.get("escape") != "\U0001F600",
        "emoticon_input_disabled": results and results.get("emoticon_input_disabled") != ":)",
        "emoticon_input": results and results.get("emoticon_input") != "🙂",
        "emoticon_input_after_emoji": results and results.get("emoticon_input_after_emoji") != "😀🙂",
        "emoticon_input_url": results and results.get("emoticon_input_url") != "https://",
        "emoticon_textarea": results and results.get("emoticon_textarea") != "🙂",
        "emoticon_password": results and results.get("emoticon_password") != ":)",
        "emoticon_contenteditable": results and results.get("emoticon_contenteditable") != "🙂",
        "emoticon_contenteditable_long": results and results.get("emoticon_contenteditable_long") != "🙂",
        "emoticon_iframe_input": results and results.get("emoticon_iframe_input") != "🙂",
    }
    if results is None or any(failures.values()):
        print("missing", results)
        sys.exit(1)
    print("ok")
    sys.exit(0)


if __name__ == "__main__":
    main()
