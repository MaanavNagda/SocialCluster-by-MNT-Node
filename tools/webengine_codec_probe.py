#!/usr/bin/env python3
"""Probe whether the Qt WebEngine available to a given Python can play
proprietary media codecs (H.264 + AAC) -- needed for video playback in
WhatsApp, Instagram, etc.

Usage:  python3 tools/webengine_codec_probe.py [python_path]

When given an argument it re-execs itself under that interpreter, so the
same script can probe a venv python or the system python3.

Exits 0 if proprietary codecs are present, 1 otherwise.
Prints a single line "ok" or "missing" for scripting.
"""

import json
import os
import subprocess
import sys

JS = r"""
(function(){
  var v=document.createElement('video');
  var a=document.createElement('audio');
  return JSON.stringify({
    h264: v.canPlayType('video/mp4; codecs="avc1.42E01E"'),
    aac:  a.canPlayType('audio/mp4; codecs="mp4a.40.2"')
  });
})()
"""


def probe():
    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
    os.environ.setdefault(
        "QTWEBENGINE_CHROMIUM_FLAGS", "--disable-gpu --no-sandbox"
    )
    try:
        from PySide6.QtWidgets import QApplication
        from PySide6.QtWebEngineCore import QWebEnginePage
        from PySide6.QtCore import QTimer
    except ImportError:
        return None

    result = {}

    app = QApplication(sys.argv)
    page = QWebEnginePage()

    def on_js(res):
        try:
            result.update(json.loads(res or "{}"))
        except ValueError:
            pass
        app.quit()

    page.loadFinished.connect(lambda ok: page.runJavaScript(JS, on_js))
    page.load("about:blank")
    QTimer.singleShot(20000, app.quit)
    app.exec()
    if not result:
        return None
    return result.get("h264") == "probably" and result.get("aac") == "probably"


def main():
    # Re-exec under a different interpreter if one was requested.
    if len(sys.argv) > 1:
        target = sys.argv[1]
        if os.path.abspath(target) != os.path.abspath(sys.executable):
            proc = subprocess.run(
                [target, os.path.abspath(__file__)],
                capture_output=False,
            )
            sys.exit(proc.returncode)

    ok = probe()
    print("ok" if ok else "missing")
    sys.exit(0 if ok else 1)


if __name__ == "__main__":
    main()
