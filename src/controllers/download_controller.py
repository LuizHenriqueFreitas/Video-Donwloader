# controller/downloader_controller

""" could be a good ideia rename this file and class
    because it is more like a storage/ history controller
    than a download controller.
"""

""" Here you will find:
    - UI interaction functions;
    - get_history() api;
    - add_item(), update_item and remove_item() functions (CRUD APIs);
    - save changes private function;
"""

from storage.history_store import HistoryStore
from storage.settings_store import SettingsStore

# main class of this file
class DownloadController:

    # initializer function
    def __init__(self, store=None, settings=None):
        self.store = store or HistoryStore()
        self.settings = settings or SettingsStore()
        self.items = self.store.load()


    """ ==============
         CRUD APIs
      ============= """
    
    # get downloads historic
    def get_history(self):
        return sorted(self.items, key=lambda x: x.created_at, reverse=True)

    # add new item to download list UI
    def add_item(self, item):
        self.items.insert(0, item)
        self._save()

    # update a download list item UI
    def update_item(self, item):
        found = False

        for i, existing in enumerate(self.items):
            if existing.id == item.id:
                self.items[i] = item
                found = True
                break
        if found:
            self._save()

    # remove an item from download list UI
    def remove_item(self, item):
        item_id = getattr(item, "id", item)
        before = len(self.items)
        self.items = [x for x in self.items if x.id != item_id]
        if len(self.items) != before:
            self._save()

    # remove all items from download list UI
    def clear_history(self):
        self.items = []
        self._save()

        
    """ =================
        UTIL FUNCTIONS
      ================ """
    
    # save download list items
    def _save(self):
        self.store.save(self.items, max_items=self.settings.get_history_count())