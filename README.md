# Social Cluster

A single desktop app (PySide6 + QtWebEngine) that aggregates multiple social
media / messaging web apps into one tabbed window, with unified system tray
badge counts and desktop notifications, so you don't need a separate PWA or
browser window per service.

## Features

- Tabbed browser view embedding each service's real web app (WhatsApp Web,
  Discord, Instagram, etc.) via `QWebEngineView`.
- Configurable list of default and custom services (`social_cluster/services.py`).
- Combined system tray icon with an aggregate unread badge across all
  services.
- Two-tier notification system:
  - **DOM scrapers** (`social_cluster/scrapers/`) parse a service's own page
    to surface real sender + message preview in desktop notifications
    (currently: WhatsApp verified working; Discord/Snapchat experimental,
    not yet live-verified).
  - **Generic fallback** poll (`NOTIFICATION_SCRIPT` in
    `social_cluster/main.py`) that shows a plain "you have new activity"
    notification for any service without a working scraper, or if a
    scraper's selectors break.
- Multiple color themes with light/dark mode (`social_cluster/themes.py`).
- Configurable tab position (left/right/top/bottom), minimize-to-tray, and
  run-in-background behavior.

## Requirements

- Python 3.10+
- PySide6 (includes QtWebEngine)
- git

## Install (one-liner)

Paste into a terminal (KDE Plasma/Wayland or any Linux desktop):

```bash
curl -fsSL https://raw.githubusercontent.com/MaanavNagda/SocialCluster/main/install.sh | bash
```

This clones the app into `~/.local/share/SocialCluster`, creates an
isolated virtualenv there, installs a `social-cluster` launcher into
`~/.local/bin`, and adds a desktop entry so "Social Cluster" appears in
your application menu. It never uses `sudo` or installs system packages;
if a system dependency is missing (e.g. `python3-venv` on Debian/Ubuntu)
it tells you the exact command to run yourself.

To update later, just re-run the same command — it does a `git pull` on
the existing install instead of re-cloning.

### Uninstall

```bash
rm -rf ~/.local/share/SocialCluster ~/.local/bin/social-cluster ~/.local/share/applications/social-cluster.desktop
rm -rf ~/.config/SocialCluster   # optional: also remove saved settings
```

## Manual setup (for development)

```bash
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
```

## Run

```bash
python main.py
```

## Tests

```bash
python -m unittest discover -s tests
```

## Project layout

```
main.py                     # entry point
social_cluster/
  main.py                   # QMainWindow, tabs, tray, notification polling
  config.py                 # load/save JSON config (XDG config dir)
  services.py               # default service list (name + URL)
  themes.py                 # color themes / stylesheet generation
  tray.py                   # tray icon SVG rendering
  icons.py                  # per-service favicon loading
  scrapers/                 # modular per-service DOM notification scrapers
tests/                       # unittest suite
```

## Adding a new DOM scraper

Each scraper module in `social_cluster/scrapers/` exports:

- `NAME` — exact service name as used in `social_cluster/services.py`
- `SCRIPT` — JS that returns `JSON.stringify({"items": [...]})` or
  `JSON.stringify({"error": "..."})`
- `STATUS` — `"verified"` or `"experimental"`

Register the new module in `social_cluster/scrapers/__init__.py`. No changes
to `social_cluster/main.py` are needed — it polls whatever's in the
registry and automatically falls back to the generic notification if a
scraper errors out repeatedly.
