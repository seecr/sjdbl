# sjdbl – Seecr Json Database Lib

Stores Python objects as plain JSON files: `<path>/<ClassName>/<id>.json`.
Storage only; searching is done by a separate index (swindl, with sil) that is
rebuilt from `Store.list()`. `doc/reference.md` is the user-facing reference (README.md the short
introduction); keep it in step with the code.

## Layout

- `sjdbl/base.py` – `Base` (models), `Proxy` (lazy references), exceptions
- `sjdbl/field.py` – `Field` types with `to_storage`/`from_storage`
- `sjdbl/store.py` – `Store`: put/get/list/delete/archive, revision check,
  `transaction()`, the commit (with `commit.log`) and recovery at open
- `sjdbl/enumerate.py` – `Enumerator` for sequential numbers
- `examples/` – runnable scripts; `CHANGELOG.md` – keep it updated

## Commands

```sh
pytest sjdbl                              # run the tests
flake8 sjdbl examples && isort --check-only sjdbl examples
PYTHONPATH=. python examples/basic.py     # run an example against this checkout
```

`env/` is the virtualenv (see the seecr-python rebuild-venv skill); the dev tools
(flake8, isort) are the `dev` dependency group in `pyproject.toml`:
`env/bin/pip install -e . --group dev`.

Releasing: give the version a `## X.Y.Z (date)` section in `CHANGELOG.md`, then push
the tag `X.Y.Z` to GitHub; `.github/workflows/publish.yml` builds it, uploads it to
PyPI (trusted publishing) and makes the GitHub release. The tag is the version
(setuptools-scm).

The sjdbl installed in site-packages may be an older release; use
`PYTHONPATH=.` (or `pip install -e .`) to test this checkout.

## Design decisions (deliberate, don't re-propose)

- Plain-text, indented JSON files; no binary format. Small-file overhead is
  handled by the file system choice.
- Single process only. Thread safety comes from one `threading.RLock` per
  `Store` (put/delete/transaction; re-entrant so transactions can nest) and a
  lock per `Enumerator`.
- Every change is a transaction (`put`/`delete` alone are one each). A
  transaction holds the store's lock until it ends and commits via `_commit`:
  temp files synced, then (more than one file) `commit.log` synced = the commit
  point, then renames/unlinks, directory fsyncs, log removed. No `os.sync()`: it
  syncs every file system on the machine.
- Recovery (finish `commit.log`, remove stray `*.tmp`) runs in `Store.__init__`,
  once per process per directory (`_opened`): a second Store on the same
  directory must not remove the temp files of a commit in progress. Finishing a
  commit is part of the transaction, not "self-healing".
- No in-memory revision cache: reading a file's revision costs microseconds,
  the fsync milliseconds (measured in the swindl benchmarks).
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
- A transaction is in the files completely or not at all, also after a crash.
  A file is never renamed into place before its contents are synced, and
  nothing is renamed or removed before the commit point. Temp files are only
  removed by a failure before the commit point, or by recovery.
- `__rev__` changes at `put()` (so `get()` / `put()` again within a
  transaction work) and is set back to the old one if the transaction is
  discarded or fails before its commit point; after the commit point it stays
  (recovery will write that revision).
- In a transaction: `get()` of the owning thread sees its puts and deletes,
  other threads and `list()` don't; an exception inside it discards it.
- The commit log names files relative to the store (`Item/<id>.json`), not
  qids; recovery refuses entries that leave the store.
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
- Code style: black, isort with the black profile (`pyproject.toml`), flake8 (`.flake8`);
  lines up to 88.
- Before every push: flake8, isort and the tests must pass. The pre-push hook
  (`.githooks/pre-push`, on with `git config core.hooksPath .githooks`, once per clone)
  runs them and stops the push otherwise; `git push --no-verify` skips it.
- Tests live next to the code (`*_test.py`), are plain pytest functions and
  use `tmp_path` for stores.
