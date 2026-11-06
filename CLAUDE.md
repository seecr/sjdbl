# sjdbl – Seecr Json Database Lib

Stores Python objects as plain JSON files: `<path>/<ClassName>/<id>.json`.
Storage only; searching is done by a separate index (swindl, Lucene) that is
rebuilt from `Store.list()`. See README.md for the user-facing docs.

## Layout

- `sjdbl/base.py` – `Base` (models), `Proxy` (lazy references), exceptions
- `sjdbl/field.py` – `Field` types with `to_storage`/`from_storage`
- `sjdbl/store.py` – `Store`: put/get/list/delete/archive, revision check,
  `batch()` for bulk loading
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
- Single process only. Thread safety comes from one `threading.RLock` per
  `Store` (put/delete/batch; re-entrant so batches can nest) and a lock per
  `Enumerator`.
- `Store.batch()` is optional: code that doesn't use it behaves as before.
  A batch holds the store's lock until it ends (other threads' put/delete
  wait), writes everything at the end with `os.sync()` before and after the
  renames (one sync for the batch instead of an fsync per file), and makes
  objects durable at the end of the batch, not per `put()`. Used for bulk
  loading, e.g. harvesting.
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
  in-memory `__rev__` is only updated after a successful write. In a batch
  `__rev__` changes at `put()` (so `get()` / `put()` again within the batch
  work) and is set back to the old one if the batch fails or is discarded.
- A batch: `get()` sees objects put in it, `list()` does not; an exception
  inside it discards the whole batch (nothing written); a file is never
  renamed into place before its contents are synced.
- `__rev__` changes in `put()`, never in `update()`.
- `Base` and `Proxy` compare and hash by `qid`.
- `Base.__init_subclass__` checks `FIELDS` at class definition (no duplicate names, no
  name of a `Base` attribute or meta field). Inherited `FIELDS` are not merged: models
  write `Parent.FIELDS + [...]`. `Base` has no `INDEX`; that is swindl's.
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
