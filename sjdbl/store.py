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


class Store:
    def __init__(self, path, models):
        self._path = path
        self._models = {}
        self._enumerators = {}
        self._lock = threading.RLock()
        self._batch = None  # qid -> (obj, old rev, data) while in batch()
        self._batch_depth = 0

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

    def put(self, *objs):
        with self._lock:
            if self._batch is not None:
                self._put_in_batch(objs)
            else:
                self._put(objs)

    @contextmanager
    def batch(self):
        """Many puts with one sync to disk, for bulk loading (e.g. harvesting).

        Inside the batch put() checks revisions and serializes as always, but
        writes nothing yet; get() sees the objects put. At the end all files
        are written as temp files, synced to disk at once (os.sync), renamed
        into place and synced again. An exception inside the batch discards
        it: nothing is written and the objects get their old revisions back.
        Objects are durable when the batch ends, not at each put(). list()
        does not see objects of an unfinished batch.
        """
        with self._lock:
            if self._batch is None:
                self._batch = {}
            self._batch_depth += 1
            try:
                yield self
            except BaseException:
                if self._batch_depth == 1:
                    self._discard_batch()
                raise
            finally:
                self._batch_depth -= 1
            if self._batch_depth == 0:
                pending, self._batch = self._batch, None
                try:
                    self._write_batch(pending)
                except BaseException:
                    for obj, old_rev, _ in pending.values():
                        obj._meta[__REV__] = old_rev
                    raise

    def _put_in_batch(self, objs):
        to_add = []
        for obj in objs:
            if obj.qid in self._batch:
                stored_rev = self._batch[obj.qid][0][__REV__]
            else:
                stored_rev = self._stored_rev(obj.qid)
            if stored_rev is not None and stored_rev != obj[__REV__]:
                raise HasChangedException(obj.qid)
            new_rev = new_uuid()
            record = obj.to_storage()
            record["meta"][__REV__] = new_rev
            to_add.append((obj, new_rev, json.dumps(record, indent=2)))
        for obj, new_rev, data in to_add:
            old_rev = (
                self._batch[obj.qid][1] if obj.qid in self._batch else obj[__REV__]
            )
            obj._meta[__REV__] = new_rev
            self._batch[obj.qid] = (obj, old_rev, data)

    def _discard_batch(self):
        pending, self._batch = self._batch, None
        for obj, old_rev, _ in (pending or {}).values():
            obj._meta[__REV__] = old_rev

    def _write_batch(self, pending):
        if not pending:
            return
        files = []
        try:
            for qid, (_, _, data) in pending.items():
                file = self._file_for_qid(qid)
                tmp_file = file.with_suffix(".tmp")
                tmp_file.write_text(data)
                files.append((tmp_file, file))
            os.sync()  # the contents are on disk before any rename
            for tmp_file, file in files:
                tmp_file.replace(file)
            os.sync()  # and the renames
        finally:
            for tmp_file, _ in files:
                tmp_file.unlink(missing_ok=True)

    def _put(self, objs):
        to_write = []
        for obj in objs:
            stored_rev = self._stored_rev(obj.qid)
            if stored_rev is not None and stored_rev != obj[__REV__]:
                raise HasChangedException(obj.qid)

            new_rev = new_uuid()
            record = obj.to_storage()
            record["meta"][__REV__] = new_rev
            to_write.append((obj, new_rev, json.dumps(record, indent=2)))

        for obj, new_rev, data in to_write:
            file = self._file_for_qid(obj.qid)
            tmp_file = file.with_suffix(".tmp")
            try:
                with tmp_file.open("w") as fp:
                    fp.write(data)
                    fp.flush()
                    os.fsync(fp.fileno())
                tmp_file.replace(file)
                fsync_dir(file.parent)
            finally:
                tmp_file.unlink(missing_ok=True)
            obj._meta[__REV__] = new_rev

    def _stored_rev(self, qid):
        if (file := self._file_for_qid(qid)).exists():
            return json.loads(file.read_text())["meta"][__REV__]

    def get(self, qid):
        try:
            file = self._file_for_qid(qid)
        except ValueError:
            return None  # not a qid of this store, so it does not exist
        batch = self._batch
        if batch is not None and qid in batch:
            cls, _ = qid.split(":", 1)
            return self._models[cls].from_storage(self, json.loads(batch[qid][2]))
        if file.exists():
            cls, _ = qid.split(":", 1)
            return self._from_file(self._models[cls], file)

    def archive(self, obj):
        obj.mark_archived(self)

    def delete(self, obj):
        with self._lock:
            qid = self._qid(obj)
            if self._batch is not None and qid in self._batch:
                del self._batch[qid]
            if (file := self._file_for_qid(qid)).exists():
                file.unlink()
                fsync_dir(file.parent)

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
        if isinstance(obj, Base):
            return obj.qid
        elif isinstance(obj, str):
            cls, _ = obj.split(":", 1)
            if cls in self._models:
                return obj
        raise ValueError(f"No qid found for: {obj}")
