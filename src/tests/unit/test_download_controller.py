# Translate and revise

"""
Testes para controller/downloader_controller.py (DownloadController)

Cobrem:
    - __init__() (injeção de dependências vs. defaults, carregamento inicial)
    - get_history() (ordenação por created_at, não destrutiva)
    - add_item() (inserção no início, persistência)
    - update_item() (substituição por id, persistência condicional)
    - remove_item() (remoção por objeto com .id ou por id "cru", persistência condicional)
    - _save() (repasse correto de items e max_items para o store)

Todas as dependências (HistoryStore, SettingsStore) são substituídas por
duplos de teste (fakes) injetados via construtor — nenhuma persistência
real em disco ocorre.
"""

import pytest

from controllers.download_controller import DownloadController


# ---------------------------------------------------------------------------
# Fakes / helpers
# ---------------------------------------------------------------------------

class FakeItem:
    def __init__(self, item_id, created_at=0, **extra):
        self.id = item_id
        self.created_at = created_at
        for k, v in extra.items():
            setattr(self, k, v)

    def __eq__(self, other):
        return isinstance(other, FakeItem) and self.id == other.id and self.created_at == other.created_at

    def __repr__(self):
        return f"FakeItem(id={self.id!r}, created_at={self.created_at!r})"


class FakeHistoryStore:
    def __init__(self, initial_items=None):
        self._initial_items = initial_items if initial_items is not None else []
        self.save_calls = []  # lista de (items_snapshot, max_items)
        self.load_called = False

    def load(self):
        self.load_called = True
        return list(self._initial_items)

    def save(self, items, max_items=None):
        # guarda uma cópia para evitar que mutações futuras de self.items
        # "vazem" para a assinatura já registrada da chamada
        self.save_calls.append((list(items), max_items))


class FakeSettingsStore:
    def __init__(self, history_count=50):
        self._history_count = history_count
        self.get_history_count_called = 0

    def get_history_count(self):
        self.get_history_count_called += 1
        return self._history_count


def make_controller(initial_items=None, history_count=50):
    store = FakeHistoryStore(initial_items)
    settings = FakeSettingsStore(history_count)
    controller = DownloadController(store=store, settings=settings)
    return controller, store, settings


# ---------------------------------------------------------------------------
# __init__
# ---------------------------------------------------------------------------

class TestInit:

    def test_uses_injected_store_and_settings(self):
        store = FakeHistoryStore([FakeItem(1, created_at=10)])
        settings = FakeSettingsStore(history_count=7)
        controller = DownloadController(store=store, settings=settings)

        assert controller.store is store
        assert controller.settings is settings

    def test_loads_items_from_store_on_init(self):
        item = FakeItem(1, created_at=10)
        store = FakeHistoryStore([item])
        controller = DownloadController(store=store, settings=FakeSettingsStore())

        assert store.load_called is True
        assert controller.items == [item]

    def test_empty_store_results_in_empty_items(self):
        controller, store, _ = make_controller(initial_items=[])
        assert controller.items == []

    def test_creates_default_history_store_when_none_provided(self, monkeypatch):
        import controllers.download_controller as dc_module

        created = {}

        class FakeDefaultHistoryStore:
            def __init__(self):
                created["history_store"] = True

            def load(self):
                return []

        monkeypatch.setattr(dc_module, "HistoryStore", FakeDefaultHistoryStore)
        controller = DownloadController(settings=FakeSettingsStore())

        assert created.get("history_store") is True
        assert isinstance(controller.store, FakeDefaultHistoryStore)

    def test_creates_default_settings_store_when_none_provided(self, monkeypatch):
        import controllers.download_controller as dc_module

        created = {}

        class FakeDefaultSettingsStore:
            def __init__(self):
                created["settings_store"] = True

            def get_history_count(self):
                return 100

        monkeypatch.setattr(dc_module, "SettingsStore", FakeDefaultSettingsStore)
        controller = DownloadController(store=FakeHistoryStore([]))

        assert created.get("settings_store") is True
        assert isinstance(controller.settings, FakeDefaultSettingsStore)


# ---------------------------------------------------------------------------
# get_history
# ---------------------------------------------------------------------------

class TestGetHistory:

    def test_sorted_descending_by_created_at(self):
        older = FakeItem(1, created_at=100)
        newer = FakeItem(2, created_at=300)
        middle = FakeItem(3, created_at=200)
        controller, _, _ = make_controller(initial_items=[older, newer, middle])

        result = controller.get_history()
        assert [i.id for i in result] == [2, 3, 1]

    def test_empty_history_returns_empty_list(self):
        controller, _, _ = make_controller(initial_items=[])
        assert controller.get_history() == []

    def test_single_item_history(self):
        item = FakeItem(1, created_at=10)
        controller, _, _ = make_controller(initial_items=[item])
        assert controller.get_history() == [item]

    def test_does_not_mutate_original_items_order(self):
        older = FakeItem(1, created_at=100)
        newer = FakeItem(2, created_at=300)
        controller, _, _ = make_controller(initial_items=[older, newer])

        controller.get_history()
        # a ordem interna de self.items não deve ser alterada por get_history
        assert [i.id for i in controller.items] == [1, 2]

    def test_returns_new_list_not_same_reference(self):
        item = FakeItem(1, created_at=10)
        controller, _, _ = make_controller(initial_items=[item])
        result = controller.get_history()
        assert result is not controller.items


# ---------------------------------------------------------------------------
# add_item
# ---------------------------------------------------------------------------

class TestAddItem:

    def test_inserts_new_item_at_beginning(self):
        existing = FakeItem(1, created_at=10)
        controller, store, _ = make_controller(initial_items=[existing])

        new_item = FakeItem(2, created_at=20)
        controller.add_item(new_item)

        assert [i.id for i in controller.items] == [2, 1]

    def test_add_to_empty_list(self):
        controller, store, _ = make_controller(initial_items=[])
        item = FakeItem(1, created_at=10)
        controller.add_item(item)
        assert controller.items == [item]

    def test_triggers_save_with_current_items_and_max_items(self):
        controller, store, settings = make_controller(initial_items=[], history_count=25)
        item = FakeItem(1, created_at=10)
        controller.add_item(item)

        assert len(store.save_calls) == 1
        saved_items, max_items = store.save_calls[0]
        assert saved_items == [item]
        assert max_items == 25
        assert settings.get_history_count_called == 1

    def test_multiple_adds_each_prepend_and_save(self):
        controller, store, _ = make_controller(initial_items=[])
        item1 = FakeItem(1, created_at=10)
        item2 = FakeItem(2, created_at=20)

        controller.add_item(item1)
        controller.add_item(item2)

        assert [i.id for i in controller.items] == [2, 1]
        assert len(store.save_calls) == 2


# ---------------------------------------------------------------------------
# update_item
# ---------------------------------------------------------------------------

class TestUpdateItem:

    def test_updates_existing_item_in_place(self):
        original = FakeItem(1, created_at=10, title="old title")
        controller, store, _ = make_controller(initial_items=[original])

        updated = FakeItem(1, created_at=10, title="new title")
        controller.update_item(updated)

        assert controller.items[0].title == "new title"
        assert controller.items[0] is updated

    def test_preserves_position_of_updated_item(self):
        item1 = FakeItem(1, created_at=30)
        item2 = FakeItem(2, created_at=20)
        item3 = FakeItem(3, created_at=10)
        controller, _, _ = make_controller(initial_items=[item1, item2, item3])

        updated_item2 = FakeItem(2, created_at=20, title="changed")
        controller.update_item(updated_item2)

        assert [i.id for i in controller.items] == [1, 2, 3]
        assert controller.items[1].title == "changed"

    def test_saves_when_item_found(self):
        item = FakeItem(1, created_at=10)
        controller, store, _ = make_controller(initial_items=[item])

        controller.update_item(FakeItem(1, created_at=10, title="x"))

        assert len(store.save_calls) == 1

    def test_does_not_save_when_item_not_found(self):
        item = FakeItem(1, created_at=10)
        controller, store, _ = make_controller(initial_items=[item])

        controller.update_item(FakeItem(999, created_at=10))

        assert len(store.save_calls) == 0
        # lista original permanece inalterada
        assert controller.items == [item]

    def test_update_first_match_only_when_duplicate_ids_exist(self):
        # cenário de dados inconsistentes: dois itens com o mesmo id
        dup1 = FakeItem(1, created_at=10, title="first")
        dup2 = FakeItem(1, created_at=20, title="second")
        controller, store, _ = make_controller(initial_items=[dup1, dup2])

        updated = FakeItem(1, created_at=10, title="updated")
        controller.update_item(updated)

        # apenas o primeiro encontrado (índice 0) é substituído
        assert controller.items[0].title == "updated"
        assert controller.items[1].title == "second"

    def test_update_on_empty_list_does_nothing(self):
        controller, store, _ = make_controller(initial_items=[])
        controller.update_item(FakeItem(1, created_at=10))
        assert controller.items == []
        assert len(store.save_calls) == 0


# ---------------------------------------------------------------------------
# remove_item
# ---------------------------------------------------------------------------

class TestRemoveItem:

    def test_removes_item_by_object_with_id_attribute(self):
        item1 = FakeItem(1, created_at=10)
        item2 = FakeItem(2, created_at=20)
        controller, store, _ = make_controller(initial_items=[item1, item2])

        controller.remove_item(item1)

        assert [i.id for i in controller.items] == [2]

    def test_removes_item_by_raw_id_value(self):
        # getattr(item, "id", item) -> se não tiver atributo "id", usa o
        # próprio valor passado como id. Testa remoção via id "cru" (int).
        item1 = FakeItem(1, created_at=10)
        item2 = FakeItem(2, created_at=20)
        controller, store, _ = make_controller(initial_items=[item1, item2])

        controller.remove_item(1)  # passando o id diretamente, não o objeto

        assert [i.id for i in controller.items] == [2]

    def test_removes_item_by_string_id(self):
        item1 = FakeItem("abc-123", created_at=10)
        controller, store, _ = make_controller(initial_items=[item1])

        controller.remove_item("abc-123")
        assert controller.items == []

    def test_saves_when_item_removed(self):
        item1 = FakeItem(1, created_at=10)
        controller, store, _ = make_controller(initial_items=[item1])

        controller.remove_item(item1)
        assert len(store.save_calls) == 1

    def test_does_not_save_when_item_not_found(self):
        item1 = FakeItem(1, created_at=10)
        controller, store, _ = make_controller(initial_items=[item1])

        controller.remove_item(FakeItem(999, created_at=10))

        assert len(store.save_calls) == 0
        assert controller.items == [item1]

    def test_remove_from_empty_list_is_noop(self):
        controller, store, _ = make_controller(initial_items=[])
        controller.remove_item(FakeItem(1, created_at=10))
        assert controller.items == []
        assert len(store.save_calls) == 0

    def test_removes_all_items_with_matching_id(self):
        # remove_item usa uma list comprehension que filtra TODOS os itens
        # com o mesmo id, não apenas o primeiro (diferente de update_item)
        dup1 = FakeItem(1, created_at=10)
        dup2 = FakeItem(1, created_at=20)
        other = FakeItem(2, created_at=30)
        controller, store, _ = make_controller(initial_items=[dup1, dup2, other])

        controller.remove_item(1)

        assert [i.id for i in controller.items] == [2]


# ---------------------------------------------------------------------------
# _save (via efeitos observados em add/update/remove)
# ---------------------------------------------------------------------------

class TestSave:

    def test_save_passes_current_items_snapshot(self):
        item1 = FakeItem(1, created_at=10)
        controller, store, _ = make_controller(initial_items=[item1])

        item2 = FakeItem(2, created_at=20)
        controller.add_item(item2)

        saved_items, _ = store.save_calls[-1]
        assert [i.id for i in saved_items] == [2, 1]

    def test_save_uses_settings_history_count_each_time(self):
        controller, store, settings = make_controller(initial_items=[], history_count=3)

        controller.add_item(FakeItem(1, created_at=10))
        controller.add_item(FakeItem(2, created_at=20))

        assert settings.get_history_count_called == 2
        assert all(max_items == 3 for _, max_items in store.save_calls)

    def test_save_reflects_updated_settings_value_dynamically(self):
        controller, store, settings = make_controller(initial_items=[], history_count=10)

        controller.add_item(FakeItem(1, created_at=10))
        settings._history_count = 5  # simula mudança de configuração em runtime
        controller.add_item(FakeItem(2, created_at=20))

        assert store.save_calls[0][1] == 10
        assert store.save_calls[1][1] == 5