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

from .base import Base, Field
from .utils import new_uuid

import copy
from uuid import UUID


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
