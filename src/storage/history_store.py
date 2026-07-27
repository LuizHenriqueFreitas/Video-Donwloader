# storage/history_store

""" Here you will find:
    - load history data api;
    - save history data api;
"""

import json
import os
from models.download_item import DownloadItem
from core.utils import get_user_data_dir

# main class from this file
class HistoryStore:
    def __init__(self, file_path=os.path.join(get_user_data_dir(), "history.json")):
        self.file_path = file_path
        os.makedirs(os.path.dirname(self.file_path), exist_ok=True)

    # load history data
    def load(self):
        if not os.path.exists(self.file_path):
            return []

        try:
            with open(self.file_path, "r", encoding="utf-8") as f:
                data = json.load(f)
                return [DownloadItem.from_dict(x) for x in data]
        except Exception:
            return []

    # save history data
    def save(self, items, max_items=50):
        # sort and apply limit
        items = sorted(items, key=lambda x: x.created_at, reverse=True)
        items = items[:max_items]

        with open(self.file_path, "w", encoding="utf-8") as f:
            json.dump([x.to_dict() for x in items], f, indent=2)