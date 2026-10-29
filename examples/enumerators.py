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

"""Sequential numbers with an enumerator."""

from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from tempfile import TemporaryDirectory

from sjdbl import Store
from sjdbl.base import Base
from sjdbl.enumerate import EnumerateValue
from sjdbl.field import Field


class Invoice(Base):
    ENUMERATORS = [EnumerateValue("number", start=1000)]
    FIELDS = [Field.int("number"), Field.str("customer")]


def main(path):
    store = Store(path=path, models=[Invoice])
    numbers = store.enumerator(Invoice, "number")

    for customer in ["Alice", "Bob"]:
        invoice = Invoice.create(number=numbers.increment(), customer=customer)
        store.put(invoice)
        print(invoice.customer, "gets invoice", invoice.number)

    print("counter file:", (path / "Invoice" / "number.enumerator").read_text())

    with ThreadPoolExecutor(max_workers=8) as executor:
        issued = list(executor.map(lambda _: numbers.increment(), range(100)))
    print("100 numbers from 8 threads, all unique:", len(set(issued)) == 100)


if __name__ == "__main__":
    with TemporaryDirectory() as tmp:
        main(Path(tmp))
