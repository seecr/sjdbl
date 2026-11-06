# Changelog

## 0.3.0 (2026-11-06)

### Breaking changes

- The fields of a model are checked when its class is defined: a `TypeError` for a field
  name that is used twice, or that clashes with an attribute of `Base` (`id`, `qid`,
  `update`, `create`, `index_values`, `__id__`, ...). Such a field used to be silently
  hidden behind the attribute.
- `Base` no longer has `INDEX = []`: sjdbl never used it. Indexing belongs to swindl, whose
  `Base` has it.

### Added

- `Store.batch()`: a context manager for bulk loading. Puts inside it are
  checked and serialized as usual but written at the end, with one sync to
  disk for the whole batch instead of an fsync per file. `get()` sees the
  objects put in the batch; an exception discards the batch.

## 0.2.0 (2026-10-30)

The file format is unchanged: files written by 0.1.0 are read by this version
and the other way around.

### Breaking changes

- `Store.put()` raises `HasChangedException` when the object on disk has a
  different revision than the object being saved. Saving a stale copy used to
  overwrite newer data silently.
- `__rev__` now changes on every `put()`, instead of on `update()`.
  `update()` still returns whether something changed, but no longer touches
  `__rev__`. Code that reads `qrid` after `update()` and before `put()` now
  gets the revision the object was loaded with.
- `Base.create(field=None)` sets the field to `None`. Previously `None` values
  were ignored and the field kept its default.
- Objects compare equal by `qid` (class name and id) instead of by id within
  the same class. A `Proxy` and the object it refers to are now equal in both
  directions.
- `Field.xml` defaults to `None` instead of `list`.

### Changed

- New ids and revisions (and `Field.uuid` defaults) are random uuid4 values
  instead of uuid1. Existing uuid1 ids stay valid.

### Added

- `Field.decimal`, stored as a string to keep the exact value.
- `HasChangedException` and `DanglingReferenceError` in `sjdbl.base`.
  `DanglingReferenceError` is a subclass of `ValueError`, which was raised
  before.
- `Base` and `Proxy` are hashable (by `qid`).
- `copy.deepcopy()` works on `Base` objects; proxies are copied unloaded.
- Stored files are indented for readability.
- `README.md`, this changelog and `examples/`.

### Fixed

- A qid is checked before it is used as a file name. `get()` returns `None` and
  `delete()` raises `ValueError` for a qid of an unknown class or with a path
  in it (`Person:../User/<id>`, `Person:../../file`): qids come from forms and
  urls and could read or delete other files.
- `Field.collection` gives every object its own list; the default list was
  shared by all new objects.
- `Field.enum` stores and loads `None`.
- After a write or delete the directory is `fsync`ed as well, so the change
  survives a power failure.
- `Store.put()` writes atomically (temporary file, `fsync`, rename). A failing
  write or an unserializable value no longer leaves an empty file behind,
  which also broke `list()`.
- `Store.put(a, b, ...)` checks and serializes all objects before writing any
  of them.
- `Store.put()`, `Store.delete()` and `Enumerator.increment()` are safe to use
  from multiple threads.
- `Enumerator` writes are `fsync`ed, so a number is not handed out twice after
  a crash.
- `mark_archived()` produces a new revision.
- Looking up dunder attributes (for example `hasattr(proxy, "__html__")`) no
  longer loads a proxy and no longer raises for dangling references.
- Saving an object with an empty `Field.xml` no longer crashes.
- `Base.archive(store)` works with a plain sjdbl `Store`; `Store.archive()`
  was missing.

## 0.1.0

- Initial release.
