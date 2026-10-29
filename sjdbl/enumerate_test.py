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

from .enumerate import EnumerateValue, Enumerator
from .store import Store
from .base import Base
from .field import Field

from concurrent.futures import ThreadPoolExecutor


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
        results = [f.result() for f in [executor.submit(increment_many) for _ in range(8)]]

    numbers = [n for result in results for n in result]
    assert sorted(numbers) == list(range(200))
