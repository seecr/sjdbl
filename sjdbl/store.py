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

import json
import logging
import os
import threading
from contextlib import contextmanager

from .base import __REV__, Base, HasChangedException, Proxy
from .enumerate import Enumerator
from .utils import fsync_dir, new_uuid

logger = logging.getLogger(__name__)

COMMIT_LOG = "commit.log"

# The store directories this process has opened. Recovery (finishing a commit that a
# crash interrupted) runs only at the first open: a second Store on the same directory
# must not touch the temporary files of a commit that is still going on.
_opened = set()
_opened_lock = threading.Lock()


class Store:
    """Objects as JSON files: <path>/<ClassName>/<id>.json.

    Every change is a transaction: a put or delete on its own, or all puts and deletes
    in a `with store.transaction():` block. A transaction is written completely or not
    at all, also when the process crashes (see _commit)."""

    def __init__(self, path, models):
        self._path = path
        self._models = {}
        self._enumerators = {}
        self._lock = threading.RLock()
        self._tx = None  # qid -> data (str), or None for a delete, in transaction()
        self._tx_revs = []  # (obj, revision before its put) in transaction()
        self._tx_depth = 0
        self._tx_thread = None  # only this thread sees the transaction's changes

        for model in models:
            if not issubclass(model, Base):
                continue
            model_name = model.__name__

            self._models[model_name] = model
            (self._path / model_name).mkdir(parents=True, exist_ok=True)

            if hasattr(model, "ENUMERATORS"):
                for enumerate_value in model.ENUMERATORS:
                    name = enumerate_value.name
                    enumerator = Enumerator(
                        self._path / model_name / f"{name}.enumerator",
                        start=enumerate_value.start,
                    )

                    if model_name not in self._enumerators:
                        self._enumerators[model_name] = {}
                    self._enumerators[model_name][name] = enumerator

        with _opened_lock:
            key = os.path.realpath(self._path)
            if key not in _opened:
                _opened.add(key)
                self._recover()

    def enumerator(self, model, name):
        return self._enumerators.get(model.__name__, {}).get(name)

    def _file_for_qid(self, qid):
        """The file of a qid. Raises ValueError for a qid that is not one of this
        store: qids come from forms and urls, so they must never reach other files."""
        cls, sep, uuid = qid.partition(":")
        if (
            not sep
            or cls not in self._models
            or uuid in ("", ".", "..")
            or any(c in uuid for c in "/\\:\0")
        ):
            raise ValueError(f"Invalid qid: {qid!r}")
        return self._path / cls / f"{uuid}.json"

    # --- transactions ---

    @contextmanager
    def transaction(self):
        """All puts and deletes in the block are written together at its end, or none
        of them (an exception in the block, or a crash before the commit).

        Inside the block put() checks revisions and serializes as always, but writes
        nothing yet; get() sees the puts and deletes, list() does not. An exception
        discards the transaction: nothing is written and the objects get their old
        revisions back. Blocks can be nested; the outermost commits. The store's lock
        is held for the whole block: other threads' puts and deletes wait, and their
        get() doesn't see the transaction's changes until it is committed."""
        with self._lock:
            if self._tx is None:
                self._tx, self._tx_revs = {}, []
                self._tx_thread = threading.get_ident()
            self._tx_depth += 1
            try:
                yield self
            except BaseException:
                if self._tx_depth == 1:
                    self._discard()
                raise
            finally:
                self._tx_depth -= 1
            if self._tx_depth == 0:
                pending, revs = self._tx, self._tx_revs
                self._tx, self._tx_revs, self._tx_thread = None, [], None
                self._commit(pending, revs)

    def _discard(self):
        revs = self._tx_revs
        self._tx, self._tx_revs, self._tx_thread = None, [], None
        _restore(revs)

    def _transaction_of_this_thread(self):
        if self._tx_thread == threading.get_ident():
            return self._tx

    def put(self, *objs):
        with self.transaction():
            to_add = []
            for obj in objs:
                stored_rev = self._stored_rev(obj.qid)
                if stored_rev is not None and stored_rev != obj[__REV__]:
                    raise HasChangedException(obj.qid)
                new_rev = new_uuid()
                record = obj.to_storage()
                record["meta"][__REV__] = new_rev
                to_add.append((obj, new_rev, json.dumps(record, indent=2)))
            for obj, new_rev, data in to_add:
                self._tx_revs.append((obj, obj[__REV__]))
                obj._meta[__REV__] = new_rev
                self._tx[obj.qid] = data

    def delete(self, obj):
        with self.transaction():
            qid = self._qid(obj)
            self._file_for_qid(qid)  # a valid qid of this store
            self._tx[qid] = None

    def archive(self, obj):
        obj.mark_archived(self)

    def _stored_rev(self, qid):
        """The revision as it is now, within the transaction."""
        if self._tx is not None and qid in self._tx:
            data = self._tx[qid]
            return None if data is None else json.loads(data)["meta"][__REV__]
        if (file := self._file_for_qid(qid)).exists():
            return json.loads(file.read_text())["meta"][__REV__]

    # --- the commit ---

    def _commit(self, pending, revs):
        """Writes a transaction: pending is qid -> JSON text, or None for a delete;
        revs the objects' revisions from before it, restored when it fails before its
        commit point.

        1. Every new version goes to a temporary file (<id>.tmp), and is synced.
        2. With more than one file: the commit log names every file; written and
           synced. This is the commit point: from here the transaction is done, and if
           the process dies now, _recover finishes it at the next start.
        3. The temporary files are renamed into place, deleted files removed, the
           directories synced.
        4. The commit log is removed.

        One file needs no log: its rename is atomic, and is the commit point."""
        if not pending:
            return
        writes = []  # (file, its temporary file, the JSON text)
        deletes = []
        for qid, data in pending.items():
            file = self._file_for_qid(qid)
            if data is None:
                deletes.append(file)
            else:
                writes.append((file, file.with_suffix(".tmp"), data))
        committed = False
        try:
            for _, tmp_file, data in writes:
                tmp_file.write_text(data)
            for _, tmp_file, _ in writes:
                _fsync_file(tmp_file)
            log = self._path / COMMIT_LOG
            with_log = len(pending) > 1
            if with_log:
                self._write_log(log, writes, deletes)
                committed = True
            for file, tmp_file, _ in writes:
                tmp_file.replace(file)
                committed = True
            for file in deletes:
                file.unlink(missing_ok=True)
                committed = True
            changed = [file for file, _, _ in writes] + deletes
            for directory in {file.parent for file in changed}:
                fsync_dir(directory)
            if with_log:
                log.unlink()
                fsync_dir(self._path)
        except BaseException:
            if not committed:
                # (a log that was written but not synced must not be finished later)
                (self._path / COMMIT_LOG).unlink(missing_ok=True)
                for _, tmp_file, _ in writes:
                    tmp_file.unlink(missing_ok=True)
                _restore(revs)
            else:
                logger.exception(
                    f"{self._path}: a committed transaction could not be finished; "
                    "it is finished when the store is opened again"
                )
            raise

    def _write_log(self, log, writes, deletes):
        relative = lambda file: file.relative_to(self._path).as_posix()  # noqa: E731
        content = json.dumps(
            {
                "write": [relative(file) for file, _, _ in writes],
                "delete": [relative(file) for file in deletes],
            }
        )
        tmp_log = log.with_suffix(".tmp")
        tmp_log.write_text(content)
        _fsync_file(tmp_log)
        tmp_log.replace(log)
        fsync_dir(self._path)

    def _recover(self):
        """At the first open: finish a transaction that was committed (its commit log
        exists) but not completely written, and remove the temporary files of one that
        never reached its commit point."""
        log = self._path / COMMIT_LOG
        if log.exists():
            entries = json.loads(log.read_text())
            directories = set()
            for name in entries["write"]:
                file = self._logged_file(name)
                tmp_file = file.with_suffix(".tmp")
                if tmp_file.exists():
                    tmp_file.replace(file)
                directories.add(file.parent)
            for name in entries["delete"]:
                file = self._logged_file(name)
                file.unlink(missing_ok=True)
                directories.add(file.parent)
            for directory in directories:
                fsync_dir(directory)
            log.unlink()
            fsync_dir(self._path)
            logger.warning(
                f"{self._path}: finished a transaction interrupted by a crash: "
                f"{len(entries['write'])} written, {len(entries['delete'])} deleted"
            )
        for tmp_file in [
            *self._path.glob("*/*.tmp"),
            *self._path.glob(f"{COMMIT_LOG[:-4]}.tmp"),
        ]:
            logger.warning(f"{tmp_file}: removed (a transaction that never committed)")
            tmp_file.unlink()

    def _logged_file(self, name):
        directory, _, file_name = name.partition("/")
        if (
            not directory
            or "/" in file_name
            or file_name in ("", ".", "..")
            or directory in (".", "..")
        ):
            raise ValueError(f"{self._path / COMMIT_LOG}: invalid entry {name!r}")
        return self._path / directory / file_name

    # --- reading ---

    def get(self, qid):
        try:
            file = self._file_for_qid(qid)
        except ValueError:
            return None  # not a qid of this store, so it does not exist
        cls, _ = qid.split(":", 1)
        tx = self._transaction_of_this_thread()
        if tx is not None and qid in tx:
            if (data := tx[qid]) is None:
                return None
            return self._models[cls].from_storage(self, json.loads(data))
        if file.exists():
            return self._from_file(self._models[cls], file)

    def list(self, cls):
        model_name = cls.__name__
        model = self._models[model_name]
        for file in (self._path / model_name).glob("*.json"):
            yield self._from_file(model, file)

    def _from_file(self, model, file):
        with file.open() as fp:
            values = json.loads(fp.read())
            return model.from_storage(self, values)

    def proxy(self, qid):
        return Proxy(self, qid)

    def _qid(self, obj):
        if isinstance(obj, (Base, Proxy)):
            return obj.qid
        elif isinstance(obj, str):
            cls, _ = obj.split(":", 1)
            if cls in self._models:
                return obj
        raise ValueError(f"No qid found for: {obj}")


def _restore(revs):
    """Back to the revisions from before the transaction (latest put first)."""
    for obj, rev in reversed(revs):
        obj._meta[__REV__] = rev


def _fsync_file(path):
    fd = os.open(path, os.O_RDONLY)
    try:
        os.fsync(fd)
    finally:
        os.close(fd)
