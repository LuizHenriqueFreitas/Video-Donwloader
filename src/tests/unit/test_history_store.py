# need to remake

import json
import pytest
from datetime import datetime, timedelta

from src.storage.history_store import HistoryStore
from src.models.download_item import DownloadItem


# ==========================
# FIXTURE: store isolado
# ==========================
@pytest.fixture
def store(tmp_path):
    file_path = tmp_path / "history.json"
    return HistoryStore(file_path=str(file_path))


# ==========================
# HELPER
# ==========================
def create_item(i):
    item = DownloadItem(
        url=f"url_{i}",
        title=f"title_{i}",
        format_type="MP4",
        quality="720p",
        thumbnail="thumb.jpg",
        status="completed"
    )
    item.id = str(i)
    item.created_at = (datetime.now() - timedelta(minutes=i)).isoformat()
    return item


# ==========================
# TESTES
# ==========================

def test_should_return_empty_if_file_not_exists(store):
    items = store.load()
    assert items == []


def test_should_save_and_load_items(store):
    items = [create_item(i) for i in range(3)]

    store.save(items)
    loaded = store.load()

    assert len(loaded) == 3
    assert loaded[0].title.startswith("title_")


def test_should_limit_to_max_stored_items(store):
    # o histórico mantém em disco o suficiente para a maior opção de exibição (50)
    items = [create_item(i) for i in range(60)]

    store.save(items)

    with open(store.file_path, "r", encoding="utf-8") as f:
        data = json.load(f)

    assert len(data) == 50


def test_should_order_by_created_at_desc(store):
    items = [create_item(i) for i in range(5)]

    store.save(items)
    loaded = store.load()

    dates = [item.created_at for item in loaded]

    assert dates == sorted(dates, reverse=True)


def test_should_handle_corrupted_file(store):
    # escreve lixo no arquivo
    with open(store.file_path, "w", encoding="utf-8") as f:
        f.write("INVALID JSON")

    items = store.load()

    assert items == []


def test_should_write_valid_json_structure(store):
    items = [create_item(i) for i in range(3)]

    store.save(items)

    with open(store.file_path, "r", encoding="utf-8") as f:
        data = json.load(f)

    assert isinstance(data, list)
    assert "title" in data[0]
    assert "url" in data[0]


def test_should_override_existing_file(store):
    items1 = [create_item(i) for i in range(2)]
    store.save(items1)

    items2 = [create_item(i) for i in range(5)]
    store.save(items2)

    loaded = store.load()

    assert len(loaded) == 5


def test_should_preserve_data_integrity(store):
    items = [create_item(i) for i in range(3)]

    store.save(items)
    loaded = store.load()

    for original, loaded_item in zip(items, loaded):
        assert original.id == loaded_item.id
        assert original.title == loaded_item.title
        assert original.url == loaded_item.url