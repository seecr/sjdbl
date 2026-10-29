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
import os
import threading

from .base import Base, Proxy, HasChangedException, __REV__
from .utils import new_uuid
from .enumerate import Enumerator

import logging

logger = logging.getLogger(__name__)


class Store:
    def __init__(self, path, models):
        self._path = path
        self._models = {}
        self._enumerators = {}
        self._lock = threading.Lock()

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
        cls, uuid = qid.split(":", 1)
        return self._path / cls / f"{uuid}.json"

    def put(self, *objs):
        with self._lock:
            self._put(objs)

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
            finally:
                tmp_file.unlink(missing_ok=True)
            obj._meta[__REV__] = new_rev

    def _stored_rev(self, qid):
        if (file := self._file_for_qid(qid)).exists():
            return json.loads(file.read_text())["meta"][__REV__]

    def get(self, qid):
        if (file := self._file_for_qid(qid)).exists():
            cls, _ = qid.split(":", 1)
            return self._from_file(self._models[cls], file)

    def archive(self, obj):
        obj.mark_archived(self)

    def delete(self, obj):
        with self._lock:
            if (file := self._file_for_qid(self._qid(obj))).exists():
                file.unlink()

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
