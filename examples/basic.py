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

"""Models, put/get/update/list/delete and what ends up on disk."""

from datetime import date
from decimal import Decimal
from enum import Enum
from pathlib import Path
from tempfile import TemporaryDirectory

from sjdbl import Store
from sjdbl.base import Base
from sjdbl.field import Field


class Category(Enum):
    book = "book"
    music = "music"


class Product(Base):
    FIELDS = [
        Field.str("title"),
        Field.decimal("price"),
        Field.enum("category", Category, Category.book),
        Field.date("released"),
        Field.bool("in_stock", default=True),
        Field.json("tags"),
    ]


def main(path):
    store = Store(path=path, models=[Product])

    product = Product.create(
        title="The Hobbit",
        price=Decimal("12.50"),
        released=date(1937, 9, 21),
        tags=["fantasy", "classic"],
    )
    store.put(product)
    print("stored:", product.qid)

    loaded = store.get(product.qid)
    print("loaded:", loaded.title, loaded.price, loaded.category, loaded.released)

    changed = loaded.update(price=Decimal("9.95"), in_stock=False)
    print("changed:", changed)
    store.put(loaded)

    store.put(Product.create(title="Abbey Road", category=Category.music))
    print("all titles:", sorted(p.title for p in store.list(Product)))

    print("\nfile on disk:")
    print((path / "Product" / f"{product.id}.json").read_text())

    store.delete(loaded)
    print("\nafter delete:", store.get(product.qid))


if __name__ == "__main__":
    with TemporaryDirectory() as tmp:
        main(Path(tmp))
