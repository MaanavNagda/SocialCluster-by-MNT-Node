import json
import os

DEFAULT_CONFIG = {
    "theme": "amethyst",
    "dark_mode": False,
    "tab_position": "left",
    "minimize_to_tray": True,
    "run_in_background": True,
    "active_services": [],
    "custom_services": [],
    "enabled_scrapers": None,
}


def _config_dir():
    xdg = os.environ.get("XDG_CONFIG_HOME")
    if xdg:
        return os.path.join(xdg, "SocialCluster")
    return os.path.join(os.path.expanduser("~"), ".config", "SocialCluster")


def _config_file():
    return os.path.join(_config_dir(), "config.json")


def _ensure_config_dir():
    os.makedirs(_config_dir(), exist_ok=True)


def load_config():
    path = _config_file()
    if not os.path.exists(path):
        return dict(DEFAULT_CONFIG)
    try:
        with open(path, "r", encoding="utf-8") as f:
            loaded = json.load(f)
        merged = dict(DEFAULT_CONFIG)
        merged.update(loaded)
        return merged
    except Exception:
        return dict(DEFAULT_CONFIG)


def save_config(config):
    _ensure_config_dir()
    with open(_config_file(), "w", encoding="utf-8") as f:
        json.dump(config, f, indent=2)
