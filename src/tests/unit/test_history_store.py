# Translate and revise

"""
Testes para storage/history_store.py (HistoryStore)

Cobrem:
    - __init__() (criação de diretório, uso de file_path customizado, e a
      peculiaridade do valor padrão de file_path ser avaliado UMA VEZ no
      momento da importação do módulo, não a cada instanciação)
    - load() (arquivo ausente, JSON válido, JSON corrompido, exceções diversas)
    - save() (ordenação por created_at, aplicação de max_items, serialização)
    - round-trip save() -> load()

A classe DownloadItem é substituída por um duplo de teste (FakeDownloadItem)
via monkeypatch no módulo storage.history_store, para não depender do
contrato exato de serialização da implementação real.
"""

import inspect
import json
import os

import pytest

import core.utils as core_utils
import storage.history_store as hs
from storage.history_store import HistoryStore


# ---------------------------------------------------------------------------
# Fakes / helpers
# ---------------------------------------------------------------------------

class FakeDownloadItem:
    def __init__(self, id=None, created_at=0, title=""):
        self.id = id
        self.created_at = created_at
        self.title = title

    def to_dict(self):
        return {"id": self.id, "created_at": self.created_at, "title": self.title}

    @classmethod
    def from_dict(cls, data):
        return cls(id=data.get("id"), created_at=data.get("created_at", 0),
                    title=data.get("title", ""))

    def __eq__(self, other):
        return (isinstance(other, FakeDownloadItem)
                and self.id == other.id
                and self.created_at == other.created_at
                and self.title == other.title)

    def __repr__(self):
        return f"FakeDownloadItem(id={self.id!r}, created_at={self.created_at!r})"


class ExplodingDownloadItem:
    """Simula uma classe cujo from_dict() lança exceção (ex.: dado malformado)."""
    @classmethod
    def from_dict(cls, data):
        raise ValueError("dado malformado")


@pytest.fixture(autouse=True)
def fake_download_item(monkeypatch):
    """Por padrão, todos os testes usam FakeDownloadItem no lugar da classe real."""
    monkeypatch.setattr(hs, "DownloadItem", FakeDownloadItem)


@pytest.fixture
def store(tmp_path):
    file_path = str(tmp_path / "sub" / "history.json")
    return HistoryStore(file_path=file_path)


# ---------------------------------------------------------------------------
# __init__
# ---------------------------------------------------------------------------

class TestInit:

    def test_stores_provided_file_path(self, tmp_path):
        file_path = str(tmp_path / "custom" / "hist.json")
        store = HistoryStore(file_path=file_path)
        assert store.file_path == file_path

    def test_creates_parent_directory(self, tmp_path):
        file_path = str(tmp_path / "a" / "b" / "c" / "history.json")
        assert not (tmp_path / "a").exists()
        HistoryStore(file_path=file_path)
        assert (tmp_path / "a" / "b" / "c").is_dir()

    def test_does_not_create_the_file_itself(self, tmp_path):
        file_path = str(tmp_path / "dir" / "history.json")
        HistoryStore(file_path=file_path)
        assert not os.path.exists(file_path)

    def test_idempotent_when_directory_already_exists(self, tmp_path):
        file_path = str(tmp_path / "dir" / "history.json")
        HistoryStore(file_path=file_path)
        # segunda instanciação não deve lançar exceção mesmo com o diretório já existente
        HistoryStore(file_path=file_path)

    def test_default_file_path_is_baked_in_at_import_time(self, monkeypatch, tmp_path):
        """Documenta uma peculiaridade real do código: o valor padrão do
        parâmetro file_path (`os.path.join(get_user_data_dir(), "history.json")`)
        é avaliado UMA VEZ, quando o módulo é importado -- não a cada chamada
        de HistoryStore(). Por isso, mesmo que get_user_data_dir() seja
        monkeypatchado DEPOIS da importação, instanciar HistoryStore() sem
        argumentos continua usando o caminho antigo já "congelado" na
        assinatura da função."""
        default_before = inspect.signature(HistoryStore.__init__).parameters["file_path"].default

        # muda o que get_user_data_dir() retornaria a partir de agora
        fake_dir = str(tmp_path / "totally_new_dir")
        monkeypatch.setattr(hs, "get_user_data_dir", lambda: fake_dir)

        # o default já foi calculado no import; não deve mudar
        default_after = inspect.signature(HistoryStore.__init__).parameters["file_path"].default
        assert default_after == default_before
        assert not default_after.startswith(fake_dir)

    def test_default_file_path_matches_get_user_data_dir_at_import(self):
        # como ninguém alterou o cwd desde o import do módulo, o default
        # deve corresponder ao valor atual de get_user_data_dir()
        expected = os.path.join(core_utils.get_user_data_dir(), "history.json")
        default = inspect.signature(HistoryStore.__init__).parameters["file_path"].default
        assert default == expected


# ---------------------------------------------------------------------------
# load()
# ---------------------------------------------------------------------------

class TestLoad:

    def test_returns_empty_list_when_file_missing(self, store):
        assert store.load() == []

    def test_loads_valid_json_into_download_items(self, store):
        data = [
            {"id": 1, "created_at": 100, "title": "video 1"},
            {"id": 2, "created_at": 200, "title": "video 2"},
        ]
        os.makedirs(os.path.dirname(store.file_path), exist_ok=True)
        with open(store.file_path, "w", encoding="utf-8") as f:
            json.dump(data, f)

        result = store.load()
        assert len(result) == 2
        assert all(isinstance(x, FakeDownloadItem) for x in result)
        assert result[0].id == 1
        assert result[1].title == "video 2"

    def test_preserves_order_from_file(self, store):
        data = [{"id": 3, "created_at": 1}, {"id": 1, "created_at": 3}, {"id": 2, "created_at": 2}]
        os.makedirs(os.path.dirname(store.file_path), exist_ok=True)
        with open(store.file_path, "w", encoding="utf-8") as f:
            json.dump(data, f)

        result = store.load()
        # load() não ordena, apenas desserializa na ordem do arquivo
        assert [x.id for x in result] == [3, 1, 2]

    def test_empty_json_array_returns_empty_list(self, store):
        os.makedirs(os.path.dirname(store.file_path), exist_ok=True)
        with open(store.file_path, "w", encoding="utf-8") as f:
            json.dump([], f)
        assert store.load() == []

    def test_malformed_json_returns_empty_list(self, store):
        os.makedirs(os.path.dirname(store.file_path), exist_ok=True)
        with open(store.file_path, "w", encoding="utf-8") as f:
            f.write("{not valid json,,,")
        assert store.load() == []

    def test_empty_file_returns_empty_list(self, store):
        os.makedirs(os.path.dirname(store.file_path), exist_ok=True)
        with open(store.file_path, "w", encoding="utf-8") as f:
            f.write("")
        assert store.load() == []

    def test_json_not_a_list_of_dicts_returns_empty_list(self, store, monkeypatch):
        os.makedirs(os.path.dirname(store.file_path), exist_ok=True)
        with open(store.file_path, "w", encoding="utf-8") as f:
            json.dump({"not": "a list"}, f)
        # iterar sobre um dict itera as chaves (strings), e from_dict(str)
        # deve estourar exceção internamente com o FakeDownloadItem real,
        # mas garantimos com uma classe que sempre lança
        monkeypatch.setattr(hs, "DownloadItem", ExplodingDownloadItem)
        assert store.load() == []

    def test_from_dict_exception_returns_empty_list(self, store, monkeypatch):
        data = [{"id": 1, "created_at": 1}]
        os.makedirs(os.path.dirname(store.file_path), exist_ok=True)
        with open(store.file_path, "w", encoding="utf-8") as f:
            json.dump(data, f)

        monkeypatch.setattr(hs, "DownloadItem", ExplodingDownloadItem)
        assert store.load() == []

    def test_file_read_error_returns_empty_list(self, store, monkeypatch):
        os.makedirs(os.path.dirname(store.file_path), exist_ok=True)
        with open(store.file_path, "w", encoding="utf-8") as f:
            json.dump([{"id": 1, "created_at": 1}], f)

        def raise_io_error(*args, **kwargs):
            raise OSError("disco cheio ou permissão negada")

        monkeypatch.setattr(hs, "open", raise_io_error, raising=False)
        assert store.load() == []


# ---------------------------------------------------------------------------
# save()
# ---------------------------------------------------------------------------

class TestSave:

    def test_writes_items_as_json(self, store):
        items = [FakeDownloadItem(id=1, created_at=10, title="a")]
        store.save(items)

        with open(store.file_path, "r", encoding="utf-8") as f:
            data = json.load(f)
        assert data == [{"id": 1, "created_at": 10, "title": "a"}]

    def test_sorts_items_descending_by_created_at(self, store):
        items = [
            FakeDownloadItem(id=1, created_at=100),
            FakeDownloadItem(id=2, created_at=300),
            FakeDownloadItem(id=3, created_at=200),
        ]
        store.save(items)

        with open(store.file_path, "r", encoding="utf-8") as f:
            data = json.load(f)
        assert [x["id"] for x in data] == [2, 3, 1]

    def test_respects_default_max_items_of_50(self, store):
        items = [FakeDownloadItem(id=i, created_at=i) for i in range(60)]
        store.save(items)

        with open(store.file_path, "r", encoding="utf-8") as f:
            data = json.load(f)
        assert len(data) == 50
        # os 50 mais recentes (created_at mais alto): ids 59..10
        assert [x["id"] for x in data] == list(range(59, 9, -1))

    def test_respects_custom_max_items(self, store):
        items = [FakeDownloadItem(id=i, created_at=i) for i in range(10)]
        store.save(items, max_items=3)

        with open(store.file_path, "r", encoding="utf-8") as f:
            data = json.load(f)
        assert [x["id"] for x in data] == [9, 8, 7]

    def test_max_items_zero_writes_empty_array(self, store):
        items = [FakeDownloadItem(id=1, created_at=1)]
        store.save(items, max_items=0)

        with open(store.file_path, "r", encoding="utf-8") as f:
            data = json.load(f)
        assert data == []

    def test_saving_empty_list_writes_empty_array(self, store):
        store.save([])
        with open(store.file_path, "r", encoding="utf-8") as f:
            data = json.load(f)
        assert data == []

    def test_overwrites_previous_content(self, store):
        store.save([FakeDownloadItem(id=1, created_at=1)])
        store.save([FakeDownloadItem(id=2, created_at=2)])

        with open(store.file_path, "r", encoding="utf-8") as f:
            data = json.load(f)
        assert [x["id"] for x in data] == [2]

    def test_does_not_mutate_input_list_order(self, store):
        item1 = FakeDownloadItem(id=1, created_at=1)
        item2 = FakeDownloadItem(id=2, created_at=2)
        original = [item1, item2]
        store.save(original)
        # `items = sorted(items, ...)` reatribui o parâmetro local, então a
        # lista original passada pelo chamador não deve ser reordenada
        assert original == [item1, item2]

    def test_items_with_equal_created_at_keep_relative_order(self, store):
        # sorted() é estável: em empates, mantém a ordem original de entrada
        item_a = FakeDownloadItem(id="a", created_at=5)
        item_b = FakeDownloadItem(id="b", created_at=5)
        store.save([item_a, item_b])

        with open(store.file_path, "r", encoding="utf-8") as f:
            data = json.load(f)
        assert [x["id"] for x in data] == ["a", "b"]

    def test_output_is_pretty_printed_with_indent(self, store):
        store.save([FakeDownloadItem(id=1, created_at=1)])
        with open(store.file_path, "r", encoding="utf-8") as f:
            content = f.read()
        assert "\n" in content  # json.dump(..., indent=2) produz múltiplas linhas


# ---------------------------------------------------------------------------
# round-trip: save() -> load()
# ---------------------------------------------------------------------------

class TestRoundTrip:

    def test_save_then_load_returns_equivalent_items(self, store):
        items = [
            FakeDownloadItem(id=1, created_at=10, title="first"),
            FakeDownloadItem(id=2, created_at=20, title="second"),
        ]
        store.save(items)
        loaded = store.load()

        # load() não reordena; mas save() já persistiu em ordem decrescente
        assert [x.id for x in loaded] == [2, 1]
        assert loaded[0].title == "second"

    def test_round_trip_respects_max_items(self, store):
        items = [FakeDownloadItem(id=i, created_at=i) for i in range(5)]
        store.save(items, max_items=2)
        loaded = store.load()
        assert [x.id for x in loaded] == [4, 3]

    def test_round_trip_with_empty_history(self, store):
        store.save([])
        assert store.load() == []