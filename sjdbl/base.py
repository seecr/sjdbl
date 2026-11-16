## begin license ##
#
# "SJDBL"(Seecr Json Database Lib) provides a simple JSON store
#
# Copyright (C) 2026 Seecr (Seek You Too B.V.) https://seecr.nl
#
# This file is part of "sjdbl"
#
# "sjdbl" is licensed under the MIT License; see the LICENSE file.
# SPDX-License-Identifier: MIT
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
        if isinstance(values, _Loaded):  # from_storage: the values are complete
            self._meta, self._data = values.meta, values.data
            return
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
        # Defaults only for what the record lacks: computing all of them first (a new
        # uuid for __id__ and __rev__, among others) took half the time of a load.
        # Through cls(), so a model's own __init__ still runs.
        return cls(
            values=_Loaded(
                _values(cls.META, store, record["meta"]),
                _values(cls.FIELDS, store, record["data"]),
            )
        )

    def __eq__(self, other):
        return isinstance(other, (Base, Proxy)) and self.qid == other.qid

    def __hash__(self):
        return hash(self.qid)


class _Loaded:
    """The complete values of a stored object, for Base.__init__ (see from_storage)."""

    __slots__ = ("meta", "data")

    def __init__(self, meta, data):
        self.meta, self.data = meta, data


def _values(fields, store, stored):
    return {
        field.name: (
            field.from_storage(store, stored[field.name])
            if field.name in stored
            else field.default
        )
        for field in fields
    }


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
