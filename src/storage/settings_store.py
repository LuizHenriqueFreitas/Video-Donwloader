# storage/settings_store.py

""" Here you will find:
    - History limiter get and set;
    - some UI settings about show warnings and auto-active trimm mode;
"""

import json
import os

from core.utils import get_user_data_dir

DEFAULTS = {
    "history_count": 20,            # limit of 10, 20 or 50
    "advanced_mode": False,         # id true active trimm mode
    "skip_remove_confirm": False,   # skip history remove warning
    "skip_playlist_warning": False, # skip download playlist warning
}

ALLOWED_HISTORY_COUNTS = (10, 20, 50)

# user preferences persistence at "data/settings.json"
class SettingsStore:
    def __init__(self, file_path=None):
        self.file_path = file_path or os.path.join(get_user_data_dir(), "settings.json")
        self._data = dict(DEFAULTS)
        self._load()


    """ =======================
        LOAD & SAVE FUNCTIONS
      ====================== """

    # load hitory function
    def _load(self):
        if not os.path.exists(self.file_path):
            return
        try:
            with open(self.file_path, "r", encoding="utf-8") as f:
                data = json.load(f)
            if isinstance(data, dict):
                self._data.update({k: data[k] for k in DEFAULTS if k in data})
        except Exception:
            # if corruptd keep defaults
            pass

    # save function
    def _save(self):
        try:
            os.makedirs(os.path.dirname(self.file_path), exist_ok=True)
            with open(self.file_path, "w", encoding="utf-8") as f:
                json.dump(self._data, f, indent=2)
        except Exception as e:
            # debug message
            print("Fail trying to save:", e)


    """ ==========================
        HISTORY GET / SET APIs
      ========================== """
    # get history limit count
    def get_history_count(self) -> int:
        value = self._data.get("history_count", DEFAULTS["history_count"])
        if value not in ALLOWED_HISTORY_COUNTS:
            return DEFAULTS["history_count"]
        return value

    # set new history limit count
    def set_history_count(self, value: int):
        if value in ALLOWED_HISTORY_COUNTS:
            self._data["history_count"] = value
            self._save()


    """  ==========================
            DIALOG STUFF
      ========================== """
    # get actual config to advanced mode
    def get_advanced_mode(self) -> bool:
        return self._get_bool("advanced_mode", DEFAULTS["advanced_mode"])

    # set new default config to adcanced mode
    def set_advanced_mode(self, value: bool):
        self._data["advanced_mode"] = bool(value)
        self._save()

    # get actual config to playlist warning
    def get_skip_playlist_warning(self) -> bool:
        return self._get_bool("skip_playlist_warning", DEFAULTS["skip_playlist_warning"])

    # set new default config to playlist warning
    def set_skip_playlist_warning(self, value: bool):
        self._set_bool("skip_playlist_warning", value)

    # get actual config to skip remove confirm
    def get_skip_remove_confirm(self) -> bool:
        return self._get_bool("skip_remove_confirm", DEFAULTS["skip_remove_confirm"])

    # set new default config to skip remove confirm
    def set_skip_remove_confirm(self, value: bool):
        self._data["skip_remove_confirm"] = bool(value)
        self._save()


    """ ==========================
        BOOLEAN ASSIST METODS
      ======================== """
    # return settings bool value
    def _get_bool(self, key: str, default: bool) -> bool:
        value = self._data.get(key, default)
        return bool(value)

    # save setting boolean value
    def _set_bool(self, key: str, value: bool):
        self._data[key] = bool(value)
        self._save()