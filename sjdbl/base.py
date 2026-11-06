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

from .field import Field

__ID__ = "__id__"
__REV__ = "__rev__"
__ARCHIVED__ = "__archived__"


class HasChangedException(Exception):
    pass


class DanglingReferenceError(ValueError):
    pass


class Base:
    META = [
        Field.uuid(__ID__),
        Field.uuid(__REV__),
        Field.bool(__ARCHIVED__, default=False),
    ]
    FIELDS = []

    def __init_subclass__(cls, **kwargs):
        super().__init_subclass__(**kwargs)
        _check_fields(cls)

    def __init__(self, values=None):
        self._meta = {field.name: field.default for field in self.META}
        self._data = {field.name: field.default for field in self.FIELDS}
        if values is not None:
            for field in self.FIELDS:
                if field.name in values:
                    self._data[field.name] = values[field.name]

    def index_values(self):
        return {}

    @classmethod
    def create(cls, **kwargs):
        return cls(values=kwargs)

    @property
    def id(self):
        return self._meta[__ID__]

    @property
    def is_archived(self):
        return self._meta[__ARCHIVED__]

    @property
    def type_name(self):
        return self.__class__.__name__

    @property
    def qid(self):
        return f"{self.type_name}:{self[__ID__]}"

    @property
    def qrid(self):
        return f"{self.type_name}:{self[__ID__]}:{self[__REV__]}"

    def update(self, **kwargs):
        changed = False
        for field in self.FIELDS:
            if field.is_readonly or field.name not in kwargs:
                continue

            value = kwargs.get(field.name)
            if self._data[field.name] != value:
                self._data[field.name] = value
                changed = True
        return changed

    def delete(self, store):
        store.delete(self)

    def archive(self, store):
        store.archive(self)

    def deletable(self, store):
        return True

    def mark_archived(self, store, archived=True):
        self._meta[__ARCHIVED__] = archived
        store.put(self)

    def __getattr__(self, name):
        if name in ("_meta", "_data"):
            raise AttributeError(name)

        if name.startswith("__") and name in self._meta:
            return self._meta[name]

        if name in self._data:
            return self._data[name]
        return getattr(super(), name)

    def __getitem__(self, name):
        if name.startswith("__") and name in self._meta:
            return self._meta[name]

        if name in self._data:
            return getattr(self, name)
        raise KeyError(name)

    def to_storage(self):
        return {
            "data": {
                field.name: field.to_storage(self._data[field.name])
                for field in self.FIELDS
            },
            "meta": {
                field.name: field.to_storage(self._meta[field.name])
                for field in self.META
            },
        }

    @classmethod
    def from_storage(cls, store, record):
        obj = cls()
        obj._meta.update(
            {
                field.name: field.from_storage(store, record["meta"][field.name])
                for field in cls.META
                if field.name in record["meta"]
            }
        )
        obj._data.update(
            {
                field.name: field.from_storage(store, record["data"][field.name])
                for field in cls.FIELDS
                if field.name in record["data"]
            }
        )
        return obj

    def __eq__(self, other):
        return isinstance(other, (Base, Proxy)) and self.qid == other.qid

    def __hash__(self):
        return hash(self.qid)


META_NAMES = {field.name for field in Base.META}

# Names a field cannot have: attribute access to fields goes through __getattr__, which
# only runs when normal lookup fails, so a field with one of these names is never seen.
RESERVED_NAMES = set(dir(Base)) | META_NAMES | {"_meta", "_data"}


def _check_fields(cls):
    """Raises TypeError, at class definition, for a field that would not work."""
    seen = set()
    for field in cls.FIELDS:
        if field.name in seen:
            raise TypeError(f"{cls.__name__}: field {field.name!r} is defined twice")
        seen.add(field.name)
        if field.name in RESERVED_NAMES:
            raise TypeError(
                f"{cls.__name__}: field {field.name!r} clashes with an attribute "
                "of Base"
            )


class Proxy:
    def __init__(self, store, qid):
        self.qid = qid
        self.store = store

    def deproxy(self):
        if (obj := self.store.get(self.qid)) is None:
            raise DanglingReferenceError(f"No object to deproxy: {self.qid}")
        object.__setattr__(self, "__class__", obj.__class__)
        object.__setattr__(self, "__dict__", obj.__dict__)

    def __getattr__(self, name):
        # qid and store are missing only when built without __init__ (copy, pickle);
        # loading then would recurse
        if name in ("qid", "store") or (
            name.startswith("__") and name.endswith("__") and name not in META_NAMES
        ):
            raise AttributeError(name)
        self.deproxy()
        return getattr(self, name)

    def __deepcopy__(self, memo):
        return Proxy(self.store, self.qid)

    def __getitem__(self, name):
        self.deproxy()
        return self.__getitem__(name)

    def __eq__(self, other):
        return isinstance(other, (Base, Proxy)) and self.qid == other.qid

    def __hash__(self):
        return hash(self.qid)
