#!/usr/bin/env python3
import json
import os
import sys
import tempfile
import time

# Must be set before QtWebEngine is initialized (i.e. before QApplication is
# created / QtWebEngineCore is imported) so that background/minimized/hidden
# service tabs keep running their JS timers and still report unread counts
# for notification badges and desktop notifications.
os.environ["QTWEBENGINE_CHROMIUM_FLAGS"] = " ".join(
    filter(
        None,
        [
            os.environ.get("QTWEBENGINE_CHROMIUM_FLAGS", ""),
            "--disable-background-timer-throttling",
            "--disable-backgrounding-occluded-windows",
            "--disable-renderer-backgrounding",
            "--disable-features=IntensiveWakeUpThrottling",
        ],
    )
)

from PySide6.QtCore import Qt, QUrl, QTimer, QCoreApplication, QLockFile, QSize, QStandardPaths
from PySide6.QtGui import QIcon, QPixmap, QFont, QPainter, QColor, QAction, QPalette
from PySide6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
    QStackedWidget, QTabWidget, QToolBar, QPushButton, QCheckBox,
    QComboBox, QFormLayout, QLabel, QLineEdit, QSystemTrayIcon, QMenu, QMessageBox,
    QListWidget, QListWidgetItem, QSizePolicy, QBoxLayout,
)
from PySide6.QtWebEngineCore import (
    QWebEnginePage, QWebEngineProfile, QWebEngineScript, QWebEngineUrlRequestInterceptor,
)
from PySide6.QtWebEngineWidgets import QWebEngineView
from PySide6.QtNetwork import QLocalServer, QLocalSocket

from social_cluster import APP_NAME, APP_TITLE, __version__
from social_cluster.services import get_default_services, get_service_by_name
from social_cluster.themes import get_theme, get_stylesheet, get_theme_names
from social_cluster.config import load_config, save_config
from social_cluster.icons import IconLoader
from social_cluster.tray import render_tray_icon
from social_cluster.scrapers import SCRAPERS
from social_cluster.unicode_input import UNICODE_INPUT_JS, UnicodeLineEditFilter


APP_ICON_PATH = os.path.join(os.path.dirname(__file__), "assets", "icon.png")

# Name for the single-instance IPC channel (QLocalServer/QLocalSocket). When
# a second instance is launched (app menu, tray, running the binary again,
# etc.) while one is already running, it connects here and asks the running
# instance to raise its window instead of showing an "already running"
# error, so relaunching always brings the GUI to front -- including when
# the app is sitting in the background/tray after "start in background" or
# after the window was closed to tray.
IPC_SERVER_NAME = "SocialClusterIPC"
IPC_SHOW_MESSAGE = b"show"


NOTIFICATION_SCRIPT = """
function sc_extract_count() {
    // Signals are checked in order of reliability and are NOT summed
    // together: once an earlier, more trustworthy signal yields a count,
    // later broader/noisier signals are skipped. Summing independent
    // heuristics caused wild over-counting (e.g. WhatsApp showing 14
    // unread when there were none) because the same unread indicator was
    // often matched by more than one selector at once.
    var title = document.title;
    var matches = title.match(/\\((\\d+)\\)/);
    if (matches) {
        var n = parseInt(matches[1], 10);
        if (!isNaN(n) && n > 0) return n;
    }

    var unreadNodes = document.querySelectorAll('[data-testid*="unread"]');
    var count = 0;
    for (var j = 0; j < unreadNodes.length; j++) {
        var n2 = parseInt(unreadNodes[j].textContent, 10);
        if (!isNaN(n2) && n2 > 0) count += n2;
    }
    if (count > 0) return count;

    var ariaNodes = document.querySelectorAll('[aria-label]');
    for (var a = 0; a < ariaNodes.length; a++) {
        var label = ariaNodes[a].getAttribute('aria-label') || '';
        var m2 = label.match(/^\\s*(\\d+)\\s+(unread|new)\\b/i);
        if (m2) {
            var n3 = parseInt(m2[1], 10);
            if (!isNaN(n3) && n3 > 0) count += n3;
        }
    }
    return count;
}
sc_extract_count();
"""

FORCE_NOTIFICATIONS_JS = """
(function() {
    if (window.__scNotificationsForced) {
        return;
    }
    window.__scNotificationsForced = true;
    if (window.Notification) {
        Object.defineProperty(Notification, 'permission', {
            get: function() { return 'granted'; },
            set: function() {},
            configurable: false
        });
        Notification.requestPermission = function(callback) {
            var result = Promise.resolve('granted');
            if (typeof callback === 'function') {
                result.then(function(r) { callback(r); });
            }
            return result;
        };
        if (Notification.requestPermission) {
            Notification.requestPermission(function() {});
        }
    }
    if (navigator.permissions) {
        var originalQuery = navigator.permissions.query;
        navigator.permissions.query = function(permissionDesc) {
            var name = (permissionDesc && permissionDesc.name) || permissionDesc;
            if (name === 'notifications' || name === 'push') {
                return Promise.resolve({
                    state: 'granted',
                    addEventListener: function() {},
                    removeEventListener: function() {}
                });
            }
            return originalQuery.apply(this, arguments);
        };
    }
})();
"""

# The scraper poll must run frequently enough that rich (sender + preview)
# notifications don't lag noticeably behind a message arriving, but the
# fallback poll (generic "you have activity") is intentionally much faster
# since it's the safety net users rely on when a scraper isn't wired up for
# a service yet, or a site's DOM has changed and broken a scraper's
# selectors. 100ms is the fastest practical QTimer interval for repeatedly
# running DOM-querying JS across every open tab without visibly starving
# the Qt event loop.
FALLBACK_POLL_INTERVAL_MS = 100
SCRAPER_POLL_INTERVAL_MS = 1000

# Number of consecutive bad/empty scraper results (JS exception, malformed
# JSON, missing "items" key) before we stop trusting a service's scraper
# and let the generic fallback poll take over its badge count and
# notifications again. Requiring several in a row avoids flapping between
# the two systems during a page reload or transient DOM state.
SCRAPER_FAIL_THRESHOLD = 3

# How long after a service tab finishes loading (page load or app launch,
# including auto-launch in the background on login/boot) to treat any
# unread state it reports as pre-existing rather than "new" -- otherwise
# every launch fires a notification for whatever was already unread before
# the app even opened, since the very first poll/scrape/favicon check has
# no prior state to compare against. Real new activity that arrives after
# this window still notifies normally.
STARTUP_GRACE_SECONDS = 8


def parse_notification_count(result):
    """Coerce a runJavaScript() result into a non-negative int count.

    QWebEnginePage.runJavaScript() marshals JS numbers to Python ``float``
    (never ``int``), so callers must not rely on ``isinstance(result, int)``.
    """
    try:
        return int(result)
    except (TypeError, ValueError):
        return 0


TAB_POSITIONS = {
    "left": QTabWidget.West,
    "right": QTabWidget.East,
    "top": QTabWidget.North,
    "bottom": QTabWidget.South,
}


# Some OAuth providers (notably Google) block sign-in with an "this
# browser or app may not be secure" error when they detect an embedded
# Chromium WebView, based on heuristics tied to the Chrome/QtWebEngine
# user agent. Spoofing Firefox's UA sidesteps that specific check. This is
# scoped to login popup windows only (via QWebEnginePage.setUrlRequestInterceptor,
# not the shared profile), so it doesn't affect the UA already working for
# the main service tabs (WhatsApp, Discord, etc.).
FIREFOX_USER_AGENT = (
    "Mozilla/5.0 (X11; Linux x86_64; rv:128.0) Gecko/20100101 Firefox/128.0"
)


class FirefoxUserAgentInterceptor(QWebEngineUrlRequestInterceptor):
    def interceptRequest(self, info):
        info.setHttpHeader(b"User-Agent", FIREFOX_USER_AGENT.encode("utf-8"))


class AppWebPage(QWebEnginePage):
    def __init__(self, profile, main_window, parent=None):
        super().__init__(profile, parent)
        self._main_window = main_window
        self.featurePermissionRequested.connect(self._on_feature_permission)

    def _on_feature_permission(self, securityOrigin, feature):
        notification_features = {QWebEnginePage.Notifications}
        if hasattr(QWebEnginePage, "PushNotifications"):
            notification_features.add(QWebEnginePage.PushNotifications)
        if feature in notification_features:
            self.setFeaturePermission(
                securityOrigin,
                feature,
                QWebEnginePage.PermissionGrantedByUser,
            )

    def createWindow(self, web_window_type):
        if not self._main_window:
            return None
        if web_window_type in (
            QWebEnginePage.WebBrowserTab,
            QWebEnginePage.WebBrowserBackgroundTab,
        ):
            return self._main_window.create_popup_tab().page()
        if web_window_type in (
            QWebEnginePage.WebDialog,
            QWebEnginePage.WebBrowserWindow,
        ):
            # "Log in with Google/Facebook/etc." buttons open their OAuth
            # flow via window.open(), which Chromium classifies as a
            # WebDialog (or occasionally WebBrowserWindow) popup rather
            # than a browser tab. Previously this case fell through to
            # `return None`, which silently drops the window.open() call
            # and makes every third-party login button do nothing. Give it
            # a real popup window instead, sharing the same profile so the
            # session cookies it sets are immediately visible to the
            # opener tab once the popup closes.
            return self._main_window.create_popup_window().page()
        return None


class AppWebView(QWebEngineView):
    def __init__(self, profile, main_window, parent=None):
        super().__init__(parent)
        self.setPage(AppWebPage(profile, main_window, self))
        if main_window is not None:
            # The page's unicode-input enable flag lives on window, so it is
            # reset by every navigation and must be re-pushed after each load.
            self.page().loadFinished.connect(
                lambda _ok: main_window._sync_unicode_flags()
            )


class TabBarList(QListWidget):
    def __init__(self, main_window, parent=None):
        super().__init__(parent)
        self.main_window = main_window

    def dropEvent(self, event):
        super().dropEvent(event)
        if self.main_window is not None:
            self.main_window._on_tabs_moved()


class MainWindow(QMainWindow):
    def __init__(self, config, profile):
        super().__init__()
        self._config = config
        self._profile = profile
        self._theme = get_theme(config["theme"], config["dark_mode"])
        self._tabs = {}
        self._icons = {}
        self._counts = {}
        self._icon_flags = {}
        self._tray = None
        self._watcher = None
        self._scraper_watcher = None
        self._active_web_notifications = []
        self._profile.setNotificationPresenter(self._present_web_notification)
        self._enabled_scrapers = set(self._config.get("enabled_scrapers") or list(SCRAPERS.keys()))
        self._scraper_ok = {}
        self._scraper_fail_count = {}
        self._scraper_seen = {}
        self._loading_grace = {}
        self._icon_loader = IconLoader(self)
        self._unicode_filter = UnicodeLineEditFilter(self._config, self._theme, self)
        self._app_icon_source = QPixmap(APP_ICON_PATH)
        self._popup_windows = []
        self._services_debounce = QTimer(self)
        self._services_debounce.setSingleShot(True)
        self._services_debounce.timeout.connect(self._do_save_services)
        self._snapshots = {"services": [], "settings": {}}
        self._setup_ui()
        self._stack.currentChanged.connect(self._on_page_changed)
        self._apply_theme()
        self._apply_tab_position()
        self._rebuild_tabs()
        self._setup_tray()
        self._setup_watcher()
        self._setup_ipc_server()
        self.setWindowTitle(APP_TITLE)
        self.resize(1280, 800)
        if not self._config.get("active_services"):
            self._stack.setCurrentIndex(1)

    def _on_page_changed(self, index):
        if index == 1:
            self._snapshots["services"] = list(self._config.get("active_services", []))
        elif index == 2:
            self._snapshots["settings"] = {
                "theme": self._config.get("theme", "amethyst"),
                "dark_mode": self._config.get("dark_mode", False),
                "tab_position": self._config.get("tab_position", "left"),
                "minimize_to_tray": self._config.get("minimize_to_tray", True),
                "run_in_background": self._config.get("run_in_background", True),
                "start_in_background": self._config.get("start_in_background", False),
                "unicode_input": self._config.get("unicode_input", True),
            }

    def _all_services(self):
        return get_default_services() + list(self._config.get("custom_services", []))

    def _find_service(self, name):
        for s in self._all_services():
            if s["name"] == name:
                return s
        return None

    def _refresh_services_list(self):
        self._services_list.clear()
        for service in get_default_services():
            item = QListWidgetItem(service["name"], self._services_list)
            item.setTextAlignment(Qt.AlignCenter)
            if service["name"] in self._config.get("active_services", []):
                item.setSelected(True)
            self._icon_loader.load_icon_for_item(service, item)

        self._custom_services_list.clear()
        for service in self._config.get("custom_services", []):
            item = QListWidgetItem(service["name"], self._custom_services_list)
            item.setTextAlignment(Qt.AlignCenter)
            if service["name"] in self._config.get("active_services", []):
                item.setSelected(True)
            self._icon_loader.load_icon_for_item(service, item)

    # ---------------- UI setup ---------------- #

    def _setup_ui(self):
        self._tool_bar = QToolBar(self)
        self.addToolBar(self._tool_bar)

        action_browser = QAction("Browser", self)
        action_browser.triggered.connect(lambda: self._stack.setCurrentIndex(0))
        self._tool_bar.addAction(action_browser)

        action_services = QAction("Services", self)
        action_services.triggered.connect(lambda: self._stack.setCurrentIndex(1))
        self._tool_bar.addAction(action_services)

        action_settings = QAction("Settings", self)
        action_settings.triggered.connect(lambda: self._stack.setCurrentIndex(2))
        self._tool_bar.addAction(action_settings)

        self._stack = QStackedWidget(self)
        self.setCentralWidget(self._stack)

        self._browser_page = self._create_browser_page()
        self._services_page = self._create_services_page()
        self._settings_page = self._create_settings_page()

        self._stack.addWidget(self._browser_page)
        self._stack.addWidget(self._services_page)
        self._stack.addWidget(self._settings_page)
        self._stack.setCurrentIndex(0)

    def _create_browser_page(self):
        page = QWidget(self)
        layout = QBoxLayout(QBoxLayout.LeftToRight, page)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        self._web_stack = QStackedWidget(self)

        self._tab_bar = TabBarList(self, self)
        self._tab_bar.setViewMode(QListWidget.ListMode)
        self._tab_bar.setIconSize(QSize(64, 64))
        self._tab_bar.setSpacing(5)
        self._tab_bar.setSelectionMode(QListWidget.SingleSelection)
        self._tab_bar.setDragEnabled(True)
        self._tab_bar.setAcceptDrops(True)
        self._tab_bar.setDragDropMode(QListWidget.InternalMove)
        self._tab_bar.setDefaultDropAction(Qt.MoveAction)
        self._tab_bar.setSizePolicy(QSizePolicy.Fixed, QSizePolicy.Expanding)
        self._tab_bar.itemClicked.connect(self._on_tab_clicked)
        self._tab_bar.setStyleSheet(
            "QListWidget::item:selected { background: transparent; border: none; outline: none; }"
            " QListWidget::item:hover { background: transparent; border: none; }"
        )

        layout.addWidget(self._tab_bar)
        layout.addWidget(self._web_stack, 1)
        return page

    def _create_services_page(self):
        page = QWidget(self)
        layout = QVBoxLayout(page)

        layout.addWidget(QLabel("Default services", self))
        self._services_list = QListWidget(self)
        self._services_list.setViewMode(QListWidget.IconMode)
        self._services_list.setFlow(QListWidget.LeftToRight)
        self._services_list.setWrapping(True)
        self._services_list.setResizeMode(QListWidget.Adjust)
        self._services_list.setIconSize(QSize(64, 64))
        self._services_list.setSpacing(10)
        self._services_list.setSelectionMode(QListWidget.MultiSelection)
        self._services_list.setDragEnabled(False)
        self._services_list.setDragDropMode(QListWidget.NoDragDrop)
        self._services_list.setAcceptDrops(False)
        self._services_list.itemSelectionChanged.connect(self._auto_save_services)
        layout.addWidget(self._services_list)

        layout.addWidget(QLabel("Custom services", self))
        self._custom_services_list = QListWidget(self)
        self._custom_services_list.setViewMode(QListWidget.IconMode)
        self._custom_services_list.setFlow(QListWidget.LeftToRight)
        self._custom_services_list.setWrapping(True)
        self._custom_services_list.setResizeMode(QListWidget.Adjust)
        self._custom_services_list.setIconSize(QSize(64, 64))
        self._custom_services_list.setSpacing(10)
        self._custom_services_list.setSelectionMode(QListWidget.MultiSelection)
        self._custom_services_list.setDragEnabled(False)
        self._custom_services_list.setDragDropMode(QListWidget.NoDragDrop)
        self._custom_services_list.setAcceptDrops(False)
        self._custom_services_list.itemSelectionChanged.connect(self._auto_save_services)
        layout.addWidget(self._custom_services_list)

        custom_form = QHBoxLayout()
        self._custom_name_edit = QLineEdit(self)
        self._custom_name_edit.setPlaceholderText("Name")
        self._custom_url_edit = QLineEdit(self)
        self._custom_url_edit.setPlaceholderText("https://example.com")
        # Per-widget install only -- installing this filter on QApplication
        # crashes PySide6 when events reach Qt-internal C++ objects.
        self._unicode_filter.install_on(self._custom_name_edit)
        self._unicode_filter.install_on(self._custom_url_edit)
        add_btn = QPushButton("Add custom service", self)
        add_btn.clicked.connect(self._add_custom_service)
        custom_form.addWidget(self._custom_name_edit)
        custom_form.addWidget(self._custom_url_edit)
        custom_form.addWidget(add_btn)
        layout.addLayout(custom_form)

        buttons = QHBoxLayout()
        select_all_btn = QPushButton("Select all", self)
        select_all_btn.clicked.connect(self._select_all_services)
        deselect_all_btn = QPushButton("Deselect all", self)
        deselect_all_btn.clicked.connect(self._deselect_all_services)
        cancel_btn = QPushButton("Cancel", self)
        cancel_btn.clicked.connect(self._cancel_services)
        buttons.addWidget(select_all_btn)
        buttons.addWidget(deselect_all_btn)
        buttons.addWidget(cancel_btn)
        layout.addLayout(buttons)

        self._refresh_services_list()
        return page

    def _create_settings_page(self):
        page = QWidget(self)
        layout = QFormLayout(page)

        self._theme_combo = QComboBox(self)
        self._theme_combo.addItems(get_theme_names())
        self._theme_combo.setCurrentText(self._config.get("theme", "amethyst"))
        self._theme_combo.currentTextChanged.connect(self._auto_save_settings)
        layout.addRow("Theme:", self._theme_combo)

        self._dark_check = QCheckBox("Dark mode", self)
        self._dark_check.setChecked(self._config.get("dark_mode", False))
        self._dark_check.toggled.connect(self._auto_save_settings)
        layout.addRow(self._dark_check)

        self._tab_position_combo = QComboBox(self)
        self._tab_position_combo.addItems(["left", "right", "top", "bottom"])
        self._tab_position_combo.setCurrentText(self._config.get("tab_position", "left"))
        self._tab_position_combo.currentTextChanged.connect(self._auto_save_settings)
        layout.addRow("Tab position:", self._tab_position_combo)

        self._minimize_check = QCheckBox("Minimize to system tray on close", self)
        self._minimize_check.setChecked(self._config.get("minimize_to_tray", True))
        self._minimize_check.toggled.connect(self._auto_save_settings)
        layout.addRow(self._minimize_check)

        self._background_check = QCheckBox("Run in the background", self)
        self._background_check.setChecked(self._config.get("run_in_background", True))
        self._background_check.toggled.connect(self._auto_save_settings)
        layout.addRow(self._background_check)

        self._start_in_background_check = QCheckBox("Start in background", self)
        self._start_in_background_check.setChecked(self._config.get("start_in_background", False))
        self._start_in_background_check.toggled.connect(self._auto_save_settings)
        layout.addRow(self._start_in_background_check)

        self._unicode_check = QCheckBox("Unicode input (Ctrl+Shift+U)", self)
        self._unicode_check.setChecked(self._config.get("unicode_input", True))
        self._unicode_check.toggled.connect(self._auto_save_settings)
        layout.addRow(self._unicode_check)

        buttons = QHBoxLayout()
        cancel_btn = QPushButton("Cancel", self)
        cancel_btn.clicked.connect(self._cancel_settings)
        reset_btn = QPushButton("Reset to defaults", self)
        reset_btn.clicked.connect(self._reset_settings)
        buttons.addWidget(cancel_btn)
        buttons.addWidget(reset_btn)
        layout.addRow(buttons)

        return page

    # ---------------- Browser tabs ---------------- #

    def _rebuild_tabs(self):
        active = self._config.get("active_services", [])
        for name in list(self._tabs.keys()):
            if name not in active:
                view = self._tabs.pop(name)
                self._web_stack.removeWidget(view)
                view.deleteLater()

        self._tab_bar.clear()

        for i, name in enumerate(active):
            service = self._find_service(name)
            if not service:
                continue

            if name in self._tabs:
                view = self._tabs[name]
            else:
                view = AppWebView(self._profile, self)
                view.setToolTip(service["name"])
                view.load(QUrl(service["url"]))
                view.iconChanged.connect(
                    lambda icon, _name=name: self._on_page_icon_changed(_name)
                )
                view.page().loadFinished.connect(
                    lambda ok, _name=name: self._on_tab_load_finished(_name)
                )
                self._tabs[name] = view

            self._web_stack.addWidget(view)
            item = QListWidgetItem("", self._tab_bar)
            item.setData(Qt.UserRole, name)
            item.setToolTip(service["name"])
            item.setTextAlignment(Qt.AlignCenter)
            self._icon_loader.load_icon(
                service,
                lambda icon, _name=name: self._on_tab_icon_loaded(_name, icon),
            )

        if self._tab_bar.count() > 0:
            self._tab_bar.setCurrentRow(0)
            self._web_stack.setCurrentIndex(0)

        self._update_tab_text()

    def create_popup_tab(self):
        view = AppWebView(self._profile, self)
        view.setToolTip("Popup")
        self._web_stack.addWidget(view)
        item = QListWidgetItem("New", self._tab_bar)
        self._tab_bar.addItem(item)
        return view

    def create_popup_window(self):
        # Real top-level window (not an app tab) for OAuth-style "Log in
        # with ..." popups, matching how a normal browser presents them.
        # Shares self._profile (via AppWebView), so cookies set here are
        # immediately visible to the tab that opened it.
        view = AppWebView(self._profile, self)
        window = QWidget(self, Qt.Window)
        window.setWindowTitle("Sign in")
        window.resize(480, 640)
        layout = QVBoxLayout(window)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(view)
        window.setAttribute(Qt.WA_DeleteOnClose)

        # Scoped to this popup only: some OAuth providers (Google in
        # particular) refuse to complete sign-in from an embedded Chromium
        # WebView ("This browser or app may not be secure"). Spoofing
        # Firefox's UA for just this window sidesteps that check without
        # touching the UA already working for the regular service tabs.
        window._ua_interceptor = FirefoxUserAgentInterceptor(view.page())
        view.page().setUrlRequestInterceptor(window._ua_interceptor)

        # Most OAuth providers call window.close() themselves once the
        # login flow finishes; honor that instead of leaving a dead popup.
        view.page().windowCloseRequested.connect(window.close)
        view.page().titleChanged.connect(
            lambda title: window.setWindowTitle(title or "Sign in")
        )

        self._popup_windows.append(window)
        window.destroyed.connect(lambda: self._forget_popup_window(window))

        window.show()
        return view

    def _forget_popup_window(self, window):
        if window in self._popup_windows:
            self._popup_windows.remove(window)

    def _on_tab_clicked(self, item):
        row = self._tab_bar.row(item)
        if row >= 0:
            self._web_stack.setCurrentIndex(row)
        name = item.data(Qt.UserRole)
        if name:
            self._icon_flags[name] = False
            self._counts[name] = 0
            self._update_tab_text()
            self._update_tray_icon()

    def _effective_count(self, name):
        if self._in_startup_grace(name):
            return 0
        count = self._counts.get(name, 0)
        if count > 0:
            return count
        return -1 if self._icon_flags.get(name) else 0

    def _on_tab_load_finished(self, name):
        self._loading_grace[name] = time.time() + STARTUP_GRACE_SECONDS

    def _sync_unicode_flags(self):
        # The injected unicode-input script reads window.__scUnicodeEnabled
        # at keydown time; push the current setting into every loaded page
        # (service tabs, popup tabs, and popup windows).
        enabled = "true" if self._config.get("unicode_input", True) else "false"
        js = f"window.__scUnicodeEnabled = {enabled};"
        for i in range(self._web_stack.count()):
            view = self._web_stack.widget(i)
            if isinstance(view, QWebEngineView) and view.page() is not None:
                view.page().runJavaScript(js)
        for window in self._popup_windows:
            for view in window.findChildren(QWebEngineView):
                if view.page() is not None:
                    view.page().runJavaScript(js)

    def _in_startup_grace(self, name):
        return time.time() < self._loading_grace.get(name, 0)

    def _on_page_icon_changed(self, name):
        current_item = self._tab_bar.currentItem()
        is_active = (
            self.isActiveWindow()
            and not self.isMinimized()
            and current_item is not None
            and current_item.data(Qt.UserRole) == name
        )
        if not is_active:
            if self._in_startup_grace(name):
                # Ignore favicon churn while the page is still settling in
                # after load/launch. Unlike _counts (which gets overwritten
                # with the current real value on every poll and so
                # self-corrects once grace ends), _icon_flags is a sticky
                # boolean that only ever clears when the tab is clicked --
                # so setting it here would leave a permanent false-positive
                # tab badge for the rest of the session, not just a
                # transient one during the grace window.
                return
            was_flagged = self._icon_flags.get(name, False)
            self._icon_flags[name] = True
            if not was_flagged and self._counts.get(name, 0) == 0:
                self._show_tray_notification(name, -1)
            self._update_tab_text()
            self._update_tray_icon()

    def _scraper_active_ok(self, name):
        return (
            name in SCRAPERS
            and name in self._enabled_scrapers
            and self._scraper_ok.get(name, True)
        )

    def _on_scraper_result(self, name, result):
        try:
            data = json.loads(result) if result else {}
        except (TypeError, ValueError):
            data = {}

        if not isinstance(data, dict) or data.get("error") or "items" not in data:
            self._scraper_fail_count[name] = self._scraper_fail_count.get(name, 0) + 1
            if self._scraper_fail_count[name] >= SCRAPER_FAIL_THRESHOLD:
                self._scraper_ok[name] = False
            return

        self._scraper_fail_count[name] = 0
        self._scraper_ok[name] = True

        items = data.get("items") or []
        seen = self._scraper_seen.setdefault(name, {})

        total = 0
        new_items = []
        current_keys = set()
        for item in items:
            sender = item.get("sender") or name
            preview = item.get("preview") or ""
            try:
                count = int(item.get("count") or 0)
            except (TypeError, ValueError):
                count = 0
            total += max(count, 0)

            key = (sender, preview)
            current_keys.add(key)
            last = seen.get(key)
            if last is None or count > last:
                new_items.append((sender, count, preview))
            seen[key] = count

        for key in list(seen.keys()):
            if key not in current_keys:
                del seen[key]

        self._counts[name] = total
        if total > 0:
            self._icon_flags[name] = False

        if new_items and not self.isActiveWindow() and not self._in_startup_grace(name):
            if len(new_items) == 1:
                sender, count, preview = new_items[0]
                title = f"{name}: {sender}"
                if count > 1:
                    message = f"{count} new messages: {preview}" if preview else f"{count} new messages"
                else:
                    message = preview or "New message"
            else:
                title = f"{name}: new messages"
                message = "\n".join(
                    f"{s} ({c}): {p or '...'}" for s, c, p in new_items
                )
            icon = self._icons.get(name)
            self._show_system_notification(title, message, icon)

        self._update_tab_text()
        self._update_tray_icon()

    def _name_for_host(self, host):
        if not host:
            return None
        for name, view in self._tabs.items():
            view_host = view.url().host()
            if view_host and view_host == host:
                return name
        return None

    def _present_web_notification(self, notification):
        # Real HTML5 Web Notifications (the same API sites use to power
        # native browser/PWA notifications, e.g. WhatsApp's "New message
        # from X: <preview>") are intercepted here instead of relying on
        # our DOM-scraping heuristic, so the KDE notification gets the
        # actual sender/content the site itself decided to show.
        origin = notification.origin()
        host = origin.host() if origin is not None else ""
        name = self._name_for_host(host)
        print(
            f"[social_cluster][debug] web notification presenter fired: "
            f"host={host!r} name={name!r} title={notification.title()!r} "
            f"message={notification.message()!r}"
        )

        title = notification.title() or (name or APP_NAME)
        if name and not title.startswith(name):
            title = f"{name}: {title}"
        message = notification.message() or ""

        icon = None
        image = notification.icon()
        if image is not None and not image.isNull():
            icon = QIcon(QPixmap.fromImage(image))
        elif name and name in self._icons:
            icon = self._icons[name]

        self._show_system_notification(title, message, icon)

        if name:
            current_item = self._tab_bar.currentItem()
            is_active = (
                self.isActiveWindow()
                and not self.isMinimized()
                and current_item is not None
                and current_item.data(Qt.UserRole) == name
            )
            if not is_active:
                self._icon_flags[name] = True
                self._update_tab_text()
                self._update_tray_icon()

        self._active_web_notifications.append(notification)
        notification.closed.connect(
            lambda n=notification: self._on_web_notification_closed(n)
        )
        notification.show()

    def _on_web_notification_closed(self, notification):
        if notification in self._active_web_notifications:
            self._active_web_notifications.remove(notification)

    def _on_tabs_moved(self):
        active = []
        for i in range(self._tab_bar.count()):
            name = self._tab_bar.item(i).data(Qt.UserRole)
            if name:
                active.append(name)
        if not active:
            return
        self._config["active_services"] = active
        save_config(self._config)

        current_view = self._web_stack.currentWidget()
        for view in list(self._tabs.values()):
            self._web_stack.removeWidget(view)
        for name in active:
            view = self._tabs.get(name)
            if view:
                self._web_stack.addWidget(view)
        if current_view is not None:
            self._web_stack.setCurrentWidget(current_view)
        self._update_tab_text()

    # ---------------- Theming ---------------- #

    def _apply_theme(self):
        self.setStyleSheet(get_stylesheet(self._theme))
        self._unicode_filter.set_theme(self._theme)
        app = QApplication.instance()
        if app is not None:
            app.setPalette(self._make_palette())
            app.setStyle("Fusion")

    def _make_palette(self):
        p = QPalette()
        p.setColor(QPalette.Window, QColor(self._theme["bg"]))
        p.setColor(QPalette.WindowText, QColor(self._theme["fg"]))
        p.setColor(QPalette.Base, QColor(self._theme["bg"]))
        p.setColor(QPalette.AlternateBase, QColor(self._theme["panel"]))
        p.setColor(QPalette.Button, QColor(self._theme["panel"]))
        p.setColor(QPalette.ButtonText, QColor(self._theme["fg"]))
        p.setColor(QPalette.Text, QColor(self._theme["fg"]))
        p.setColor(QPalette.Highlight, QColor(self._theme["primary"]))
        p.setColor(QPalette.HighlightedText, QColor("#ffffff"))
        p.setColor(QPalette.ToolTipBase, QColor(self._theme["panel"]))
        p.setColor(QPalette.ToolTipText, QColor(self._theme["fg"]))
        return p

    def _apply_tab_position(self):
        direction_map = {
            "left": QBoxLayout.LeftToRight,
            "right": QBoxLayout.RightToLeft,
            "top": QBoxLayout.TopToBottom,
            "bottom": QBoxLayout.BottomToTop,
        }
        direction = direction_map.get(self._config.get("tab_position", "left"), QBoxLayout.LeftToRight)
        self._browser_page.layout().setDirection(direction)

        pos = self._config.get("tab_position", "left")
        if pos in ("left", "right"):
            self._tab_bar.setFlow(QListWidget.TopToBottom)
            self._tab_bar.setFixedWidth(90)
            self._tab_bar.setSizePolicy(QSizePolicy.Fixed, QSizePolicy.Expanding)
        else:
            self._tab_bar.setFlow(QListWidget.LeftToRight)
            self._tab_bar.setFixedHeight(90)
            self._tab_bar.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)

    # ---------------- Settings ---------------- #

    def _auto_save_services(self):
        self._services_debounce.stop()
        self._services_debounce.start(300)

    def _do_save_services(self):
        selected = set()
        for i in range(self._services_list.count()):
            item = self._services_list.item(i)
            if item.isSelected():
                selected.add(item.text())
        for i in range(self._custom_services_list.count()):
            item = self._custom_services_list.item(i)
            if item.isSelected():
                selected.add(item.text())

        current = list(self._config.get("active_services", []))
        active = [name for name in current if name in selected]
        for name in selected:
            if name not in active:
                active.append(name)

        self._config["active_services"] = active
        save_config(self._config)
        self._rebuild_tabs()

    def _select_all_services(self):
        for i in range(self._services_list.count()):
            self._services_list.item(i).setSelected(True)
        for i in range(self._custom_services_list.count()):
            self._custom_services_list.item(i).setSelected(True)

    def _deselect_all_services(self):
        for i in range(self._services_list.count()):
            self._services_list.item(i).setSelected(False)
        for i in range(self._custom_services_list.count()):
            self._custom_services_list.item(i).setSelected(False)

    def _cancel_services(self):
        self._config["active_services"] = list(self._snapshots["services"])
        save_config(self._config)
        self._refresh_services_list()
        self._rebuild_tabs()

    def _add_custom_service(self):
        name = self._custom_name_edit.text().strip()
        url = self._custom_url_edit.text().strip()
        if not name or not url:
            return
        if not url.startswith(("http://", "https://")):
            url = "https://" + url
        custom = list(self._config.get("custom_services", []))
        if any(c["name"] == name for c in custom):
            return
        custom.append({"name": name, "url": url})
        self._config["custom_services"] = custom
        if name not in self._config.get("active_services", []):
            self._config["active_services"] = list(self._config.get("active_services", [])) + [name]
        save_config(self._config)
        self._custom_name_edit.clear()
        self._custom_url_edit.clear()
        self._refresh_services_list()
        self._rebuild_tabs()

    def _auto_save_settings(self):
        self._config["theme"] = self._theme_combo.currentText()
        self._config["dark_mode"] = self._dark_check.isChecked()
        self._config["tab_position"] = self._tab_position_combo.currentText()
        self._config["minimize_to_tray"] = self._minimize_check.isChecked()
        self._config["run_in_background"] = self._background_check.isChecked()
        self._config["start_in_background"] = self._start_in_background_check.isChecked()
        self._config["unicode_input"] = self._unicode_check.isChecked()
        save_config(self._config)

        self._theme = get_theme(self._config["theme"], self._config["dark_mode"])
        self._apply_theme()
        self._apply_tab_position()
        self._sync_unicode_flags()

        app = QApplication.instance()
        if app is not None:
            app.setQuitOnLastWindowClosed(not self._config.get("run_in_background", True))

    def _cancel_settings(self):
        for key in (
            "theme", "dark_mode", "tab_position", "minimize_to_tray",
            "run_in_background", "start_in_background", "unicode_input",
        ):
            self._config[key] = self._snapshots["settings"][key]
        save_config(self._config)
        self._theme_combo.setCurrentText(self._config["theme"])
        self._dark_check.setChecked(self._config["dark_mode"])
        self._tab_position_combo.setCurrentText(self._config["tab_position"])
        self._minimize_check.setChecked(self._config["minimize_to_tray"])
        self._background_check.setChecked(self._config["run_in_background"])
        self._start_in_background_check.setChecked(self._config["start_in_background"])
        self._unicode_check.setChecked(self._config["unicode_input"])
        self._auto_save_settings()

    def _reset_settings(self):
        defaults = {
            "theme": "amethyst",
            "dark_mode": False,
            "tab_position": "left",
            "minimize_to_tray": True,
            "run_in_background": True,
            "start_in_background": False,
            "unicode_input": True,
        }
        for key, value in defaults.items():
            self._config[key] = value
        save_config(self._config)
        self._theme_combo.setCurrentText(self._config["theme"])
        self._dark_check.setChecked(self._config["dark_mode"])
        self._tab_position_combo.setCurrentText(self._config["tab_position"])
        self._minimize_check.setChecked(self._config["minimize_to_tray"])
        self._background_check.setChecked(self._config["run_in_background"])
        self._start_in_background_check.setChecked(self._config["start_in_background"])
        self._unicode_check.setChecked(self._config["unicode_input"])
        self._auto_save_settings()

    # ---------------- System tray ---------------- #

    def _setup_tray(self):
        if not QSystemTrayIcon.isSystemTrayAvailable():
            return

        self._tray = QSystemTrayIcon(self)
        self._tray.activated.connect(self._on_tray_activated)
        self._tray.setContextMenu(self._create_tray_menu())
        self._update_tray_icon()
        self._tray.show()

    def _create_tray_menu(self):
        menu = QMenu(self)
        show_action = QAction("Show", self)
        show_action.triggered.connect(self._show_window)
        menu.addAction(show_action)
        quit_action = QAction("Quit", self)
        quit_action.triggered.connect(QApplication.instance().quit)
        menu.addAction(quit_action)
        return menu

    def _tray_icon(self, badge=0):
        top = None
        if badge != 0 and self._counts:
            positive = {n: c for n, c in self._counts.items() if c > 0}
            if positive:
                top = max(positive, key=lambda n: positive[n])
        if top and top in self._icons:
            source = self._icons[top].pixmap(64, 64)
            if not source.isNull():
                pm = QPixmap(64, 64)
                pm.fill(Qt.transparent)
                painter = QPainter(pm)
                painter.setRenderHint(QPainter.Antialiasing)
                painter.drawPixmap(0, 0, source)
                if badge != 0:
                    painter.setBrush(QColor("#ff3b30"))
                    painter.setPen(Qt.NoPen)
                    painter.drawEllipse(40, 40, 20, 20)
                    if badge > 0:
                        painter.setPen(Qt.white)
                        font = QFont("sans-serif", 10)
                        font.setBold(True)
                        painter.setFont(font)
                        text = "99+" if badge > 99 else str(badge)
                        painter.drawText(40, 40, 20, 20, Qt.AlignCenter, text)
                painter.end()
                return QIcon(pm)

        # Default tray/app icon: the Social Cluster logo, with the usual
        # red badge overlay drawn on top when there's aggregate unread
        # activity but no single "top" service icon to attach it to yet
        # (e.g. favicons still loading).
        if not self._app_icon_source.isNull():
            source = self._app_icon_source.scaled(
                64, 64, Qt.KeepAspectRatio, Qt.SmoothTransformation
            )
            pm = QPixmap(64, 64)
            pm.fill(Qt.transparent)
            painter = QPainter(pm)
            painter.setRenderHint(QPainter.Antialiasing)
            x = (64 - source.width()) // 2
            y = (64 - source.height()) // 2
            painter.drawPixmap(x, y, source)
            if badge != 0:
                painter.setBrush(QColor("#ff3b30"))
                painter.setPen(Qt.NoPen)
                painter.drawEllipse(40, 40, 20, 20)
                if badge > 0:
                    painter.setPen(Qt.white)
                    font = QFont("sans-serif", 10)
                    font.setBold(True)
                    painter.setFont(font)
                    text = "99+" if badge > 99 else str(badge)
                    painter.drawText(40, 40, 20, 20, Qt.AlignCenter, text)
            painter.end()
            return QIcon(pm)

        svg = render_tray_icon(badge, self._theme["primary"])
        image = QPixmap()
        if image.loadFromData(svg.encode("utf-8"), "svg"):
            return QIcon(image)

        # Fallback: hand-draw a simple icon
        pm = QPixmap(64, 64)
        pm.fill(QColor(self._theme["primary"]))
        painter = QPainter(pm)
        painter.setPen(Qt.white)
        font = QFont("sans-serif", 20)
        font.setBold(True)
        painter.setFont(font)
        painter.drawText(pm.rect(), Qt.AlignCenter, "SC")
        if badge != 0:
            painter.setBrush(QColor("#ff3b30"))
            painter.setPen(Qt.NoPen)
            painter.drawEllipse(40, 4, 20, 20)
            if badge > 0:
                painter.setPen(Qt.white)
                font = QFont("sans-serif", 10)
                font.setBold(True)
                painter.setFont(font)
                painter.drawText(40, 4, 20, 20, Qt.AlignCenter, str(badge))
        painter.end()
        return QIcon(pm)

    def _update_tray_icon(self):
        names = set(self._counts) | set(self._icon_flags)
        effective = [self._effective_count(n) for n in names]
        total = sum(c for c in effective if c > 0)
        if total == 0 and any(c < 0 for c in effective):
            total = -1
        icon = self._tray_icon(total)
        self.setWindowIcon(icon)
        if self._tray is not None:
            self._tray.setIcon(icon)

    def _on_tray_activated(self, reason):
        if reason == QSystemTrayIcon.Trigger:
            self._show_window()

    def _show_window(self):
        self.showNormal()
        self.raise_()
        self.activateWindow()

    # ---------------- Single-instance IPC ---------------- #

    def _setup_ipc_server(self):
        # Clean up a socket file left behind by a previous crash before
        # listening, otherwise QLocalServer.listen() fails with
        # AddressInUseError even though no instance is actually running.
        QLocalServer.removeServer(IPC_SERVER_NAME)
        self._ipc_server = QLocalServer(self)
        self._ipc_server.newConnection.connect(self._on_ipc_connection)
        self._ipc_server.listen(IPC_SERVER_NAME)

    def _on_ipc_connection(self):
        socket = self._ipc_server.nextPendingConnection()
        if socket is None:
            return
        socket.readyRead.connect(lambda s=socket: self._on_ipc_data(s))
        socket.disconnected.connect(socket.deleteLater)

    def _on_ipc_data(self, socket):
        data = bytes(socket.readAll())
        if data.strip() == IPC_SHOW_MESSAGE:
            self._show_window()
        socket.disconnectFromServer()

    # ---------------- Notification watcher ---------------- #

    def _setup_watcher(self):
        self._watcher = QTimer(self)
        self._watcher.timeout.connect(self._poll_fallback)
        self._watcher.start(FALLBACK_POLL_INTERVAL_MS)

        self._scraper_watcher = QTimer(self)
        self._scraper_watcher.timeout.connect(self._poll_scrapers)
        self._scraper_watcher.start(SCRAPER_POLL_INTERVAL_MS)

    def _poll_fallback(self):
        for name, view in self._tabs.items():
            page = view.page()
            if page is None:
                continue
            page.runJavaScript(NOTIFICATION_SCRIPT, lambda result, n=name: self._on_count(n, result))

    def _poll_scrapers(self):
        for name, view in self._tabs.items():
            if name not in SCRAPERS or name not in self._enabled_scrapers:
                continue
            page = view.page()
            if page is None:
                continue
            page.runJavaScript(
                SCRAPERS[name], lambda result, n=name: self._on_scraper_result(n, result)
            )

    def _on_count(self, name, result):
        # A scraper that is currently trusted for this service owns its
        # badge count and notifications; the fallback poll only takes over
        # once that scraper has failed enough times in a row (see
        # _on_scraper_result / SCRAPER_FAIL_THRESHOLD).
        if self._scraper_active_ok(name):
            return

        count = parse_notification_count(result)
        old = self._counts.get(name, 0)
        self._counts[name] = count
        if count > 0:
            self._icon_flags[name] = False

        if count > old and count > 0 and not self._in_startup_grace(name):
            self._show_tray_notification(name, count)

        self._update_tab_text()
        self._update_tray_icon()

    def _on_tab_icon_loaded(self, name, icon):
        self._icons[name] = icon
        self._update_tab_text()

    def _make_badge_icon(self, icon, count):
        if count == 0:
            return icon
        source = icon.pixmap(64, 64)
        if source.isNull():
            return icon
        pm = QPixmap(64, 64)
        pm.fill(Qt.transparent)
        painter = QPainter(pm)
        painter.setRenderHint(QPainter.Antialiasing)
        painter.drawPixmap(0, 0, source)
        painter.setBrush(QColor("#ff3b30"))
        painter.setPen(Qt.NoPen)
        painter.drawEllipse(40, 4, 20, 20)
        if count > 0:
            painter.setPen(Qt.white)
            font = QFont("sans-serif", 10)
            font.setBold(True)
            painter.setFont(font)
            text = "99+" if count > 99 else str(count)
            painter.drawText(40, 4, 20, 20, Qt.AlignCenter, text)
        painter.end()
        return QIcon(pm)

    def _update_tab_text(self):
        for i in range(self._tab_bar.count()):
            item = self._tab_bar.item(i)
            name = item.data(Qt.UserRole)
            if not name:
                continue
            count = self._effective_count(name)
            if count > 0:
                tooltip = f"{name}: {count}"
            elif count < 0:
                tooltip = f"{name}: new activity"
            else:
                tooltip = name
            item.setToolTip(tooltip)
            if name in self._icons:
                item.setIcon(self._make_badge_icon(self._icons[name], count))

    def _show_system_notification(self, title, message, icon=None):
        if self._tray is None:
            return False
        # QSystemTrayIcon.showMessage() sends the desktop notification via
        # the platform's native (C++) D-Bus integration, which correctly
        # marshals argument types (e.g. UINT32 replaces_id, string-array
        # actions) under org.freedesktop.Notifications. Do not hand-roll
        # this over PySide6's QtDBus bindings: QVariant is not exposed to
        # Python there (PYSIDE-1904), so integer/array arguments cannot be
        # forced to the correct D-Bus type and the daemon rejects the call
        # with "UnknownMethod".
        if icon is not None:
            self._tray.showMessage(title, message, icon)
        else:
            self._tray.showMessage(title, message)
        return True

    def _show_tray_notification(self, name, count):
        if count < 0:
            title = f"{name}: new activity"
            message = f"You have new activity in {name}."
        else:
            title = f"{name}: {count} notification(s)"
            message = f"You have {count} new notification(s) in {name}."
        icon = self._icons.get(name)
        self._show_system_notification(title, message, icon)

    # ---------------- Window events ---------------- #

    def closeEvent(self, event):
        if self._tray is not None and self._config.get("minimize_to_tray", True):
            self.hide()
            event.ignore()
        else:
            event.accept()


def main():
    app = QApplication(sys.argv)
    app.setApplicationName(APP_NAME)
    app.setApplicationVersion(__version__)
    app.setOrganizationName("socialcluster")
    app.setStyle("Fusion")
    if os.path.exists(APP_ICON_PATH):
        app.setWindowIcon(QIcon(APP_ICON_PATH))

    # Use a current Chrome user agent so sites like WhatsApp Web allow the browser.
    user_agent = (
        "Mozilla/5.0 (X11; Linux x86_64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/128.0.0.0 Safari/537.36"
    )
    profile = QWebEngineProfile("SocialCluster", app)
    profile.setHttpUserAgent(user_agent)
    profile.setHttpCacheType(QWebEngineProfile.DiskHttpCache)
    profile.setPersistentCookiesPolicy(QWebEngineProfile.ForcePersistentCookies)
    base = QStandardPaths.writableLocation(QStandardPaths.ConfigLocation)
    cache_path = os.path.join(base, "SocialCluster", "cache")
    storage_path = os.path.join(base, "SocialCluster", "storage")
    os.makedirs(cache_path, exist_ok=True)
    os.makedirs(storage_path, exist_ok=True)
    profile.setCachePath(cache_path)
    profile.setPersistentStoragePath(storage_path)

    script_ready = QWebEngineScript()
    script_ready.setName("force-notifications-ready")
    script_ready.setSourceCode(FORCE_NOTIFICATIONS_JS)
    script_ready.setInjectionPoint(QWebEngineScript.DocumentReady)
    script_ready.setWorldId(QWebEngineScript.MainWorld)
    script_ready.setRunsOnSubFrames(True)
    profile.scripts().insert(script_ready)

    script_deferred = QWebEngineScript()
    script_deferred.setName("force-notifications-deferred")
    script_deferred.setSourceCode(FORCE_NOTIFICATIONS_JS)
    script_deferred.setInjectionPoint(QWebEngineScript.Deferred)
    script_deferred.setWorldId(QWebEngineScript.MainWorld)
    script_deferred.setRunsOnSubFrames(True)
    profile.scripts().insert(script_deferred)

    # Ctrl+Shift+U unicode codepoint entry inside web-app text fields
    # (QtWebEngine doesn't route IBus's unicode input to web content).
    # DocumentCreation so the keydown listener exists before the page can
    # receive input; the script is dormant until the shortcut is pressed.
    script_unicode = QWebEngineScript()
    script_unicode.setName("unicode-input")
    script_unicode.setSourceCode(UNICODE_INPUT_JS)
    script_unicode.setInjectionPoint(QWebEngineScript.DocumentCreation)
    script_unicode.setWorldId(QWebEngineScript.MainWorld)
    script_unicode.setRunsOnSubFrames(True)
    profile.scripts().insert(script_unicode)

    lock_path = os.path.join(tempfile.gettempdir(), "social_cluster.lock")
    lock = QLockFile(lock_path)
    if not lock.tryLock(100):
        # Another instance is already running (e.g. relaunched from the app
        # menu/tray, or the window is hidden after "start in background" /
        # closing to tray). Ask it to raise its window instead of just
        # erroring out, so relaunching always brings the GUI to front.
        socket = QLocalSocket()
        socket.connectToServer(IPC_SERVER_NAME)
        if socket.waitForConnected(200):
            socket.write(IPC_SHOW_MESSAGE)
            socket.flush()
            socket.waitForBytesWritten(200)
            socket.disconnectFromServer()
            sys.exit(0)
        QMessageBox.critical(None, APP_TITLE, f"{APP_NAME} is already running.")
        sys.exit(1)
    app.aboutToQuit.connect(lock.unlock)

    config = load_config()
    app.setQuitOnLastWindowClosed(not config.get("run_in_background", True))

    window = MainWindow(config, profile)
    start_hidden = (
        config.get("start_in_background", False)
        and QSystemTrayIcon.isSystemTrayAvailable()
    )
    if not start_hidden:
        window.show()
    sys.exit(app.exec())
