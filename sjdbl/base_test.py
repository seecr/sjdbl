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

import copy
from uuid import UUID

import pytest

from .base import Base, Field
from .utils import new_uuid


def test_update():
    class Some_Object(Base):
        FIELDS = [Field.str("name")]

    so = Some_Object()
    assert so.update() is False

    assert so.update(name="name") is True
    assert so.update(name="name") is False
    assert so.update(name="another name") is True


class Book(Base):
    FIELDS = [Field.str("title"), Field.str("subtitle", default="none")]


def test_create_with_none_value():
    assert Book.create(title="x").subtitle == "none"
    assert Book.create(title="x", subtitle=None).subtitle is None


def test_equality_and_hash():
    book = Book.create(title="x")
    other = Book.create(title="x")

    assert book == book
    assert book != other
    assert book != "not a book"
    assert {book, book, other} == {book, other}


def test_deepcopy():
    book = Book.create(title="x")
    book_copy = copy.deepcopy(book)

    assert book_copy == book
    assert book_copy is not book
    book_copy.update(title="y")
    assert book.title == "x"


def test_ids_are_random_uuids():
    book = Book.create(title="x")
    assert UUID(book.id).version == 4
    assert UUID(book.__rev__).version == 4
    assert UUID(new_uuid()).version == 4


def test_field_defined_twice():
    with pytest.raises(TypeError, match="Twice: field 'name' is defined twice"):

        class Twice(Base):
            FIELDS = [Field.str("name"), Field.str("name")]


def test_inherited_fields_are_not_merged():
    class Parent(Base):
        FIELDS = [Field.str("name")]

    class Child(Parent):
        FIELDS = Parent.FIELDS + [Field.int("age")]

    assert [f.name for f in Child.FIELDS] == ["name", "age"]
    assert Child.create(name="x", age=3).age == 3


@pytest.mark.parametrize(
    "name", ["id", "qid", "qrid", "type_name", "update", "delete", "create",
             "is_archived", "index_values", "to_storage", "__id__", "__rev__",
             "__archived__", "_data", "FIELDS", "__init__"]
)
def test_field_clashes_with_base(name):
    with pytest.raises(TypeError, match=f"field '{name}' clashes"):

        class Clash(Base):
            FIELDS = [Field.str(name)]


def test_base_has_no_index():
    assert not hasattr(Base, "INDEX")


def test_loading_runs_init_and_fills_in_missing_fields(tmp_path):
    """from_storage builds the object through the model's own __init__, and gives a
    field that the stored file lacks (added to the model later) its default."""
    from .store import Store

    class Note(Base):
        FIELDS = [Field.str("text")]

        def __init__(self, *args, **kwargs):
            super().__init__(*args, **kwargs)
            self.cache = "made by __init__"

    store = Store(path=tmp_path, models=[Note])
    note = Note.create(text="hello")
    store.put(note)

    class Note(Base):  # the next version of the model: a new field
        FIELDS = [Field.str("text"), Field.json("tags", default=list)]

        def __init__(self, *args, **kwargs):
            super().__init__(*args, **kwargs)
            self.cache = "made by __init__"

    again = Store(path=tmp_path, models=[Note]).get(note.qid)
    assert again.text == "hello" and again.tags == [] and again.id == note.id
    assert again.cache == "made by __init__"
    assert again.__rev__ == note.__rev__
