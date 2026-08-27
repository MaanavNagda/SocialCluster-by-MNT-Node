import os
from urllib.parse import urlparse

from PySide6.QtCore import QStandardPaths, QUrl, Qt, QSize
from PySide6.QtGui import QIcon, QPixmap, QPainter, QFont, QColor, QImage
from PySide6.QtNetwork import QNetworkAccessManager, QNetworkRequest, QNetworkReply

ICON_SIZE = 64


def _favicon_host(url):
    host = urlparse(url).hostname or ""
    parts = host.split(".")
    if len(parts) > 2:
        if parts[0] in ("www", "web", "mail", "app", "mobile", "my"):
            return ".".join(parts[1:])
    return host


def _favicon_url(url):
    return f"https://www.google.com/s2/favicons?domain={_favicon_host(url)}&sz=64"


def _remove_white_background(pm):
    if pm.isNull():
        return pm
    image = pm.toImage().convertToFormat(QImage.Format_ARGB32)
    w, h = image.width(), image.height()
    if w == 0 or h == 0:
        return pm
    threshold = 245
    stack = []
    visited = set()
    for x in range(w):
        for y in (0, h - 1):
            stack.append((x, y))
            visited.add((x, y))
    for y in range(1, h - 1):
        for x in (0, w - 1):
            stack.append((x, y))
            visited.add((x, y))
    while stack:
        x, y = stack.pop()
        c = image.pixelColor(x, y)
        if c.alpha() == 0:
            pass
        elif c.red() >= threshold and c.green() >= threshold and c.blue() >= threshold:
            image.setPixelColor(x, y, Qt.transparent)
        else:
            continue
        for dx, dy in ((1, 0), (-1, 0), (0, 1), (0, -1)):
            nx, ny = x + dx, y + dy
            if 0 <= nx < w and 0 <= ny < h and (nx, ny) not in visited:
                visited.add((nx, ny))
                stack.append((nx, ny))
    return QPixmap.fromImage(image)


def _square_pixmap(pm):
    if pm.isNull():
        return QPixmap(ICON_SIZE, ICON_SIZE)
    square = QPixmap(ICON_SIZE, ICON_SIZE)
    square.fill(Qt.transparent)
    painter = QPainter(square)
    painter.setRenderHint(QPainter.Antialiasing)
    scaled = pm.scaled(ICON_SIZE, ICON_SIZE, Qt.KeepAspectRatio, Qt.SmoothTransformation)
    x = (ICON_SIZE - scaled.width()) // 2
    y = (ICON_SIZE - scaled.height()) // 2
    painter.drawPixmap(x, y, scaled)
    painter.end()
    return square


def _placeholder_icon(service):
    colors = [
        "#9b59b6", "#e74c3c", "#34495e", "#f39c12", "#2ecc71",
        "#3498db", "#1abc9c", "#e91e63", "#607d8b", "#795548",
    ]
    letter = (service.get("name") or "?")[0].upper()
    color = colors[ord(letter) % len(colors)]
    pixmap = QPixmap(ICON_SIZE, ICON_SIZE)
    pixmap.fill(Qt.transparent)
    painter = QPainter(pixmap)
    painter.setRenderHint(QPainter.Antialiasing)
    painter.setBrush(QColor(color))
    painter.setPen(Qt.NoPen)
    painter.drawRoundedRect(0, 0, ICON_SIZE, ICON_SIZE, 16, 16)
    painter.setPen(Qt.white)
    font = QFont("sans-serif", 26)
    font.setBold(True)
    painter.setFont(font)
    painter.drawText(pixmap.rect(), Qt.AlignCenter, letter)
    painter.end()
    return QIcon(pixmap)


class IconLoader:
    def __init__(self, parent=None):
        self._manager = QNetworkAccessManager(parent)
        base = QStandardPaths.writableLocation(QStandardPaths.ConfigLocation)
        self._cache_dir = os.path.join(base, "SocialCluster", "icons")
        os.makedirs(self._cache_dir, exist_ok=True)

    def _cache_path(self, service):
        host = _favicon_host(service["url"])
        return os.path.join(self._cache_dir, f"{host}.png")

    def load_icon(self, service, set_icon):
        placeholder = _placeholder_icon(service)
        set_icon(placeholder)

        cache_path = self._cache_path(service)
        if os.path.exists(cache_path):
            pm = _square_pixmap(_remove_white_background(QPixmap(cache_path)))
            if not pm.isNull():
                set_icon(QIcon(pm))
                return

        request = QNetworkRequest(QUrl(_favicon_url(service["url"])))
        reply = self._manager.get(request)

        def _on_finished():
            if reply.error() == QNetworkReply.NoError:
                data = reply.readAll()
                if data:
                    with open(cache_path, "wb") as f:
                        f.write(bytes(data))
                    pm = _square_pixmap(_remove_white_background(QPixmap(cache_path)))
                    if not pm.isNull():
                        set_icon(QIcon(pm))
            reply.deleteLater()

        reply.finished.connect(_on_finished)

    def load_icon_for_item(self, service, item):
        item.setTextAlignment(Qt.AlignCenter)
        self.load_icon(service, item.setIcon)
