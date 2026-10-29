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

"""References, collections and lazy loading through Proxy."""

from pathlib import Path
from tempfile import TemporaryDirectory

from sjdbl import Store
from sjdbl.base import Base, DanglingReferenceError, Proxy
from sjdbl.field import Field


class Author(Base):
    FIELDS = [Field.str("name")]


class Book(Base):
    FIELDS = [
        Field.str("title"),
        Field.reference("author"),
        Field.collection("related"),
    ]


def main(path):
    store = Store(path=path, models=[Author, Book])

    tolkien = Author.create(name="J.R.R. Tolkien")
    hobbit = Book.create(title="The Hobbit", author=tolkien)
    lotr = Book.create(title="The Lord of the Rings", author=tolkien, related=[hobbit])
    store.put(tolkien, hobbit, lotr)

    book = store.get(lotr.qid)
    print("author is a proxy:", isinstance(book.author, Proxy))
    print("qid without loading:", book.author.qid)
    print("equal without loading:", book.author == tolkien)
    print("still a proxy:", isinstance(book.author, Proxy))

    print("author name:", book.author.name)
    print("now loaded:", isinstance(book.author, Author))

    print("related:", [related.title for related in book.related])

    store.delete(tolkien)
    book = store.get(lotr.qid)
    print("hasattr on dangling proxy:", hasattr(book.author, "__html__"))
    try:
        book.author.name
    except DanglingReferenceError as e:
        print("dangling reference:", e)


if __name__ == "__main__":
    with TemporaryDirectory() as tmp:
        main(Path(tmp))
