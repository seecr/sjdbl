## begin license ##
#
# "SJDBL"(Seecr Json Database Lib) provides a simple JSON store
#
# Copyright (C) 2026 Seecr (Seek You Too B.V.) https://seecr.nl
#
# This file is part of "sjdbl"
#
# "sjdbl" is free software; you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation; either version 2 of the License, or
# (at your option) any later version.
#
# "sjdbl" is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with "sjdbl"; if not, write to the Free Software
# Foundation, Inc., 51 Franklin St, Fifth Floor, Boston, MA  02110-1301  USA
#
## end license ##

import pytest

from .base import Base, HasChangedException
from .field import Field
from .store import Store


class Item(Base):
    FIELDS = [Field.str("name"), Field.int("count")]


def make_store(tmp_path):
    return Store(path=tmp_path, models=[Item])


def test_batch_writes_at_the_end(tmp_path):
    store = make_store(tmp_path)
    with store.batch():
        items = [Item.create(name=f"item {nr}") for nr in range(10)]
        store.put(*items)
        assert not list(tmp_path.glob("Item/*.json"))  # nothing written yet
        assert store.get(items[3].qid).name == "item 3"  # but get sees it
    assert 10 == len(list(tmp_path.glob("Item/*.json")))
    assert not list(tmp_path.glob("Item/*.tmp"))
    again = make_store(tmp_path)
    assert "item 3" == again.get(items[3].qid).name
    assert items[3]["__rev__"] == again.get(items[3].qid)["__rev__"]


def test_get_update_put_in_one_batch(tmp_path):
    store = make_store(tmp_path)
    item = Item.create(name="a", count=0)
    store.put(item)
    with store.batch():
        for _ in range(3):
            current = store.get(item.qid)
            current.update(count=current.count + 1)
            store.put(current)
    assert 3 == make_store(tmp_path).get(item.qid).count


def test_conflict_in_batch(tmp_path):
    store = make_store(tmp_path)
    item = Item.create(name="a")
    store.put(item)
    stale = store.get(item.qid)
    with store.batch():
        item.update(name="b")
        store.put(item)
        stale.update(name="c")
        with pytest.raises(HasChangedException):
            store.put(stale)
    assert "b" == store.get(item.qid).name


def test_exception_discards_the_batch(tmp_path):
    store = make_store(tmp_path)
    item = Item.create(name="a")
    store.put(item)
    rev = item["__rev__"]
    with pytest.raises(RuntimeError):
        with store.batch():
            item.update(name="b")
            store.put(item)
            store.put(Item.create(name="new"))
            raise RuntimeError("stop")
    assert rev == item["__rev__"]
    assert "a" == store.get(item.qid).name
    assert 1 == len(list(tmp_path.glob("Item/*.json")))
    store.put(item)  # the object is usable again


def test_nested_batch_and_delete(tmp_path):
    store = make_store(tmp_path)
    keep, gone = Item.create(name="keep"), Item.create(name="gone")
    with store.batch():
        with store.batch():
            store.put(keep, gone)
        assert not list(tmp_path.glob("Item/*.json"))
        store.delete(gone)
    assert store.get(gone.qid) is None
    assert "keep" == store.get(keep.qid).name
