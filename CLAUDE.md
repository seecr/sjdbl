# sjdbl – Seecr Json Database Lib

Stores Python objects as plain JSON files: `<path>/<ClassName>/<id>.json`.
Storage only; searching is done by a separate index (swindl, Lucene) that is
rebuilt from `Store.list()`. See README.md for the user-facing docs.

## Layout

- `sjdbl/base.py` – `Base` (models), `Proxy` (lazy references), exceptions
- `sjdbl/field.py` – `Field` types with `to_storage`/`from_storage`
- `sjdbl/store.py` – `Store`: put/get/list/delete/archive, revision check
- `sjdbl/enumerate.py` – `Enumerator` for sequential numbers
- `examples/` – runnable scripts; `CHANGELOG.md` – keep it updated

## Commands

```sh
pytest sjdbl                              # run the tests
PYTHONPATH=. python examples/basic.py     # run an example against this checkout
```

The sjdbl installed in site-packages may be an older release; use
`PYTHONPATH=.` (or `pip install -e .`) to test this checkout.

## Design decisions (deliberate, don't re-propose)

- Plain-text, indented JSON files; no binary format. Small-file overhead is
  handled by the file system choice.
- Single process only. Thread safety comes from one `threading.Lock` per
  `Store` (put/delete) and per `Enumerator`.
- `list()` reads every file; it exists for offline reindexing, not searching.
- `Field.json` stores JSON as a string inside the record. It is used in
  production data, so changing it needs a migration.
- ids and revisions are uuid4: no implicit data (time, MAC) in ids. Put
  timestamps in explicit fields.
- Datetimes are timezone-aware (seecr_stdlib); the swindl index stores UTC.

## Invariants to keep

- `put()` checks the revision on disk against `obj.__rev__` for every object,
  serializes all of them, and only then writes. A conflict or serialization
  error must leave every file untouched.
- Writes are atomic: temp file, flush, `fsync`, `replace`. The object's
  in-memory `__rev__` is only updated after a successful write.
- `__rev__` changes in `put()`, never in `update()`.
- `Base` and `Proxy` compare and hash by `qid`.
- `Proxy.__getattr__` must not load for dunder names (except the meta names
  `__id__`, `__rev__`, `__archived__`) or for `qid`/`store`.
- The stored file format (`{"data": ..., "meta": ...}`) must stay readable by
  older versions.

## Conventions

- Every source file starts with the SJDBL license header (copy it from
  `sjdbl/base.py`); `doc/license.conf` describes it.
- Code style: black, isort with the black profile.
- Tests live next to the code (`*_test.py`), are plain pytest functions and
  use `tmp_path` for stores.
- When Johan is working with Claude, commit messages start with `JJ: `; other people's
  commits don't need it.
