THEMES = {
    "amethyst": {"primary": "#9b59b6", "secondary": "#8e44ad"},
    "ruby": {"primary": "#e74c3c", "secondary": "#c0392b"},
    "onyx": {"primary": "#34495e", "secondary": "#2c3e50"},
    "pearl": {"primary": "#7f8c8d", "secondary": "#95a5a6"},
    "amber": {"primary": "#f39c12", "secondary": "#d35400"},
    "emerald": {"primary": "#2ecc71", "secondary": "#27ae60"},
    "sapphire": {"primary": "#3498db", "secondary": "#2980b9"},
}

LIGHT = {
    "bg": "#ffffff",
    "fg": "#1a1a1a",
    "panel": "#f5f5f5",
    "border": "#cccccc",
    "input_bg": "#ffffff",
}

DARK = {
    "bg": "#1e1e1e",
    "fg": "#f0f0f0",
    "panel": "#2a2a2a",
    "border": "#444444",
    "input_bg": "#333333",
}


def get_theme_names():
    return list(THEMES.keys())


def get_theme(name, dark=False):
    base = DARK if dark else LIGHT
    colors = THEMES.get(name, THEMES["amethyst"])
    return {**base, **colors, "name": name, "dark": dark}


def get_stylesheet(theme):
    if not theme:
        theme = get_theme("amethyst")
    return f"""
QMainWindow, QWidget {{
    background-color: {theme['bg']};
    color: {theme['fg']};
}}
QToolBar {{
    background-color: {theme['panel']};
    border: none;
}}
QPushButton, QToolButton, QComboBox, QCheckBox {{
    background-color: {theme['panel']};
    color: {theme['fg']};
    border: 1px solid {theme['border']};
    padding: 6px 10px;
    border-radius: 4px;
}}
QPushButton:hover, QToolButton:hover {{
    background-color: {theme['secondary']};
    color: #ffffff;
}}
QComboBox {{
    background-color: {theme['panel']};
}}
QComboBox::drop-down {{
    border: none;
}}
QListWidget {{
    background-color: {theme['panel']};
    color: {theme['fg']};
    border: 1px solid {theme['border']};
}}
QListWidget::item {{
    padding: 8px;
}}
QListWidget::item:selected {{
    background-color: {theme['primary']};
    color: #ffffff;
}}
QTabWidget::pane {{
    border: 1px solid {theme['border']};
}}
QTabBar::tab {{
    background-color: {theme['panel']};
    color: {theme['fg']};
    padding: 8px;
    border: 1px solid {theme['border']};
}}
QTabBar::tab:selected {{
    background-color: {theme['primary']};
    color: #ffffff;
}}
QTabBar::tab:hover {{
    background-color: {theme['secondary']};
}}
QLabel {{
    color: {theme['fg']};
}}
QLineEdit {{
    background-color: {theme['input_bg']};
    color: {theme['fg']};
    border: 1px solid {theme['border']};
    padding: 4px;
}}
"""
