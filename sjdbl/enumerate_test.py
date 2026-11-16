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

from concurrent.futures import ThreadPoolExecutor

from .base import Base
from .enumerate import EnumerateValue, Enumerator
from .field import Field
from .store import Store


class Person(Base):
    ENUMERATORS = [EnumerateValue("number")]
    FIELDS = Base.FIELDS + [
        Field.str("name"),
        Field.int("number"),
    ]


def test_enumerator_files(tmp_path):
    store = Store(path=tmp_path, models=[Person])

    assert (tmp_path / "Person" / "number.enumerator").is_file()
    assert (tmp_path / "Person" / "number.enumerator").read_text() == "0"

    e = store.enumerator(Person, "number")
    value = e.increment()
    assert value == 0
    assert (tmp_path / "Person" / "number.enumerator").read_text() == "1"


def test_increment_from_threads(tmp_path):
    enumerator = Enumerator(tmp_path / "number.enumerator")

    def increment_many():
        return [enumerator.increment() for _ in range(25)]

    with ThreadPoolExecutor(max_workers=8) as executor:
        futures = [executor.submit(increment_many) for _ in range(8)]
        results = [f.result() for f in futures]

    numbers = [n for result in results for n in result]
    assert sorted(numbers) == list(range(200))
