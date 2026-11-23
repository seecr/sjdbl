# sjdbl – Seecr Json Database Lib

[![Tests](https://github.com/seecr/sjdbl/actions/workflows/test.yml/badge.svg)](https://github.com/seecr/sjdbl/actions/workflows/test.yml)
[![PyPI](https://img.shields.io/pypi/v/sjdbl.svg)](https://pypi.org/project/sjdbl/)

Stores Python objects as plain JSON files: one file per object, one directory per
class. Crash-safe transactions, revisions against lost updates, lazy references,
sequential numbers. No server, no query language: searching belongs in an index that
can be rebuilt from the files at any time.

```python
from pathlib import Path

from sjdbl import Store
from sjdbl.base import Base
from sjdbl.field import Field


class Person(Base):
    FIELDS = [Field.str("name"), Field.date("dob"), Field.reference("parent")]


store = Store(path=Path("data"), models=[Person])
john = Person.create(name="John Smith")
store.put(john)                              # data/Person/<id>.json

with store.transaction():                    # all of it, or nothing
    john.update(name="John Doe")
    store.put(john, Person.create(name="Joe", parent=john))
```

- **Plain text.** Every object is a readable, indented JSON file: `cat`, `grep`, `diff`
  and fix it by hand.
- **No server.** A store is a directory; a backup is a copy of it.
- **Crash safe.** A transaction is in the files completely or not at all, also when the
  machine dies halfway.

Install with `pip install sjdbl`. It needs Python 3.11 or newer, lxml and pytest
(the tests are part of the package).

The [reference](https://github.com/seecr/sjdbl/blob/master/doc/reference.md) describes
everything; [examples](https://github.com/seecr/sjdbl/tree/master/examples) has runnable
scripts; the [changelog](https://github.com/seecr/sjdbl/blob/master/CHANGELOG.md) says
what changed.

MIT licensed, see [LICENSE](https://github.com/seecr/sjdbl/blob/master/LICENSE). By
[Seecr](https://seecr.nl).
