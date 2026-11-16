## begin license ##
#
# "SJDBL"(Seecr Json Database Lib) provides a simple JSON store
#
# Copyright (C) 2026 Seecr (Seek You Too B.V.) https://seecr.nl
#
# This file is part of "sjdbl"
#
# "sjdbl" is licensed under the MIT License; see the LICENSE file.
# SPDX-License-Identifier: MIT
#
## end license ##

"""Crash safety: a transaction is in the files completely or not at all, also when the
process dies halfway through writing it."""

import json
import threading
from pathlib import Path

import pytest

from . import store as store_module
from .base import Base
from .field import Field
from .store import COMMIT_LOG, Store


class Item(Base):
    FIELDS = [Field.str("name")]


class Crash(BaseException):
    """Stands for the process dying: nothing after it runs (no cleanup)."""


def open_store(path):
    """A Store as after a restart: recovery runs."""
    store_module._opened.discard(str(Path(path).resolve()))
    return Store(path=path, models=[Item])


def names(path):
    return sorted(item.name for item in open_store(path).list(Item))


def files(path, pattern):
    return sorted(p.name for p in Path(path).glob(pattern))


@pytest.fixture
def store(tmp_path):
    store = open_store(tmp_path)
    a, b, c = (Item.create(name=n) for n in "abc")
    store.put(a, b, c)
    store.items = (a, b, c)
    return store


def change(store):
    """One transaction: a and b renamed, c deleted, d new."""
    a, b, c = store.items
    with store.transaction():
        a.update(name="A")
        b.update(name="B")
        store.put(a, b)
        store.delete(c)
        store.put(Item.create(name="d"))


def test_a_transaction_is_written_completely(store, tmp_path):
    change(store)
    assert names(tmp_path) == ["A", "B", "d"]
    assert files(tmp_path, "*/*.tmp") == [] and not (tmp_path / COMMIT_LOG).exists()


def test_crash_before_the_commit_point_changes_nothing(store, tmp_path, monkeypatch):
    def crash(*args):
        raise Crash()

    monkeypatch.setattr(Store, "_write_log", crash)
    with pytest.raises(Crash):
        change(store)
    monkeypatch.undo()
    assert names(tmp_path) == ["a", "b", "c"]
    assert files(tmp_path, "*/*.tmp") == []


def test_temporary_files_of_a_crash_are_removed_at_open(store, tmp_path):
    """The process died while writing temporary files: no commit log, so the
    transaction never happened."""
    a, _, _ = store.items
    (tmp_path / "Item" / f"{a.id}.tmp").write_text('{"half')
    (tmp_path / "Item" / "new.tmp").write_text("{}")
    assert names(tmp_path) == ["a", "b", "c"]
    assert files(tmp_path, "*/*.tmp") == []


@pytest.mark.parametrize("renames_done", [0, 1, 2])
def test_crash_after_the_commit_point_is_finished_at_open(
    store, tmp_path, monkeypatch, renames_done
):
    original_replace = Path.replace
    renames = []

    def replace(self, target):
        if self.name != COMMIT_LOG[:-4] + ".tmp":  # not the log itself
            if len(renames) == renames_done:
                raise Crash()
            renames.append(self)
        return original_replace(self, target)

    monkeypatch.setattr(Path, "replace", replace)
    with pytest.raises(Crash):
        change(store)
    monkeypatch.undo()
    assert (tmp_path / COMMIT_LOG).exists()

    assert names(tmp_path) == ["A", "B", "d"]
    assert files(tmp_path, "*/*.tmp") == [] and not (tmp_path / COMMIT_LOG).exists()


def test_crash_while_deleting_is_finished_at_open(store, tmp_path, monkeypatch):
    original_unlink = Path.unlink

    def unlink(self, missing_ok=False):
        if self.suffix == ".json":
            raise Crash()
        return original_unlink(self, missing_ok=missing_ok)

    monkeypatch.setattr(Path, "unlink", unlink)
    with pytest.raises(Crash):
        change(store)
    monkeypatch.undo()
    assert names(tmp_path) == ["A", "B", "d"]


def test_one_file_needs_no_commit_log(tmp_path, monkeypatch):
    store = open_store(tmp_path)
    logs = []
    monkeypatch.setattr(Store, "_write_log", lambda *args: logs.append(args))
    item = Item.create(name="a")
    store.put(item)
    store.delete(item)
    assert logs == []


def test_a_failed_write_before_the_commit_point_keeps_revisions(store, monkeypatch):
    a, b, c = store.items
    revs = [a.__rev__, b.__rev__]

    def full(*args):
        raise OSError("No space left on device")

    monkeypatch.setattr(Store, "_write_log", full)
    with pytest.raises(OSError):
        change(store)
    assert [a.__rev__, b.__rev__] == revs
    monkeypatch.undo()
    change(store)  # the objects can be saved again


def test_the_log_names_files_not_qids(store, tmp_path, monkeypatch):
    logged = []
    original = Store._write_log

    def write_log(self, log, writes, deletes):
        original(self, log, writes, deletes)
        logged.append(json.loads(log.read_text()))

    monkeypatch.setattr(Store, "_write_log", write_log)
    change(store)
    a, b, c = store.items
    assert f"Item/{a.id}.json" in logged[0]["write"]
    assert logged[0]["delete"] == [f"Item/{c.id}.json"]


def test_a_log_with_a_path_outside_the_store_is_refused(tmp_path):
    open_store(tmp_path)
    (tmp_path / COMMIT_LOG).write_text(json.dumps({"write": [], "delete": ["../x"]}))
    with pytest.raises(ValueError):
        open_store(tmp_path)


def test_a_second_store_on_the_same_directory_does_not_recover(store, tmp_path):
    """Recovery is for a fresh start: a second Store opened in the same process must
    not remove the temporary files of a commit that is still going on."""
    tmp_file = tmp_path / "Item" / "busy.tmp"
    tmp_file.write_text("{}")
    Store(path=tmp_path, models=[Item])
    assert tmp_file.exists()


def test_other_threads_do_not_see_an_uncommitted_transaction(store):
    a, _, _ = store.items
    seen = []
    with store.transaction():
        a.update(name="A")
        store.put(a)
        thread = threading.Thread(target=lambda: seen.append(store.get(a.qid).name))
        thread.start()
        thread.join()
        assert store.get(a.qid).name == "A"
    assert seen == ["a"]
    assert store.get(a.qid).name == "A"


def test_delete_in_a_transaction(store):
    a, b, _ = store.items
    with store.transaction():
        store.delete(a)
        assert store.get(a.qid) is None
        store.put(Item.create(name="x"))
    assert store.get(a.qid) is None


def test_an_exception_also_undoes_deletes(store, tmp_path):
    a, _, _ = store.items
    with pytest.raises(RuntimeError):
        with store.transaction():
            store.delete(a)
            raise RuntimeError()
    assert names(tmp_path) == ["a", "b", "c"]
