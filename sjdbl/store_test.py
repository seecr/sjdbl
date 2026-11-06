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

import copy
import json
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime
from decimal import Decimal
from enum import Enum

import pytest

from .base import Base, DanglingReferenceError, HasChangedException, Proxy
from .enumerate import EnumerateValue
from .field import Field
from .store import Store


class GenderEnum(Enum):
    male = 1
    female = 2
    other = 3


class Person(Base):
    ENUMERATORS = [EnumerateValue("number")]
    FIELDS = Base.FIELDS + [
        Field.str("name"),
        Field.int("number"),
        Field.date("dob"),
        Field.reference("parent"),
        Field.enum("gender", GenderEnum, GenderEnum.other),
        Field.bool("long_hair", default=False),
        Field.uuid("gov_id"),
        Field.uuid("secret_id", default=None),
    ]


def test_enumerator_files(tmp_path):
    store = Store(path=tmp_path, models=[Person])

    assert (tmp_path / "Person" / "number.enumerator").is_file()
    assert (tmp_path / "Person" / "number.enumerator").read_text() == "0"

    e = store.enumerator(Person, "number")
    value = e.increment()
    assert value == 0
    assert (tmp_path / "Person" / "number.enumerator").read_text() == "1"


def test_store_create_and_get(tmp_path):
    store = Store(path=tmp_path, models=[Person])

    parent = Person.create(
        name="John Smith",
        dob=datetime.fromisoformat("2000-01-01"),
        gender=GenderEnum.male,
    )
    child = Person.create(
        name="Joe Smith",
        dob=datetime.fromisoformat("2020-01-01"),
        parent=parent,
        long_hair=True,
    )

    store.put(parent, child)

    parent_revisited = store.get(parent.qid)
    assert parent_revisited.__id__ == parent.__id__
    assert parent_revisited.name == "John Smith"
    assert parent_revisited.dob == datetime.fromisoformat("2000-01-01").date()
    assert parent_revisited.gender == GenderEnum.male
    assert parent_revisited.long_hair is False

    child_revisited = store.get(child.qid)
    assert child_revisited.__id__ == child.__id__
    assert child_revisited.parent.qid == parent_revisited.qid
    assert child_revisited.parent.name == "John Smith"
    assert child_revisited.gender == GenderEnum.other
    assert child_revisited.long_hair is True

    child_revisited = store.get(child.qid)
    child_revisited.parent.update(name="Jane Smith", gender=GenderEnum.female)
    store.put(child_revisited.parent)
    parent_revisited = store.get(parent.qid)
    assert parent_revisited.__id__ == parent.__id__
    assert parent_revisited.name == "Jane Smith"

    parent_revisited = store.get(parent.qid)
    assert parent_revisited["name"] == "Jane Smith"
    assert parent_revisited["gender"] == GenderEnum.female

    child_revisited = store.get(child.qid)
    child_revisited.parent["name"] == "Jane Smith"

    child_revisited = store.get(child.qid)
    assert child_revisited.parent == parent_revisited


def test_delete_as_object(tmp_path):
    store = Store(path=tmp_path, models=[Person])

    person = Person.create(name="John Smith", dob=datetime.fromisoformat("2000-01-01"))
    store.put(person)

    person_revisited = store.get(person.qid)
    assert person_revisited is not None

    store.delete(person)
    person_revisited = store.get(person.qid)
    assert person_revisited is None


def test_delete_with_qid(tmp_path):
    store = Store(path=tmp_path, models=[Person])

    person = Person.create(name="John Smith", dob=datetime.fromisoformat("2000-01-01"))
    store.put(person)

    person_revisited = store.get(person.qid)
    assert person_revisited is not None

    store.delete(person.qid)
    person_revisited = store.get(person.qid)
    assert person_revisited is None


def test_list_objects(tmp_path):
    store = Store(path=tmp_path, models=[Person])

    persons = list(store.list(Person))
    assert len(persons) == 0

    store.put(
        Person.create(name="John Smith", dob=datetime.fromisoformat("2000-01-01"))
    )
    persons = list(store.list(Person))
    assert len(persons) == 1


def test_readonly(tmp_path):
    person = Person.create(name="John Smith", dob=datetime.fromisoformat("2000-01-01"))
    person_id = person.__id__

    person.update(__id__="aap")
    assert person.__id__ == person_id


def test_none_for_uuid(tmp_path):
    person = Person.create(name="John Smith", dob=datetime.fromisoformat("2000-01-01"))
    assert person.gov_id is not None
    assert person.secret_id is None


def test_store_decimal(tmp_path):
    class Product(Base):
        FIELDS = [Field.decimal("price"), Field.decimal("discount")]

    store = Store(path=tmp_path, models=[Product])

    product = Product.create(price=Decimal("9.95"))
    store.put(product)

    stored = json.loads((tmp_path / "Product" / f"{product.id}.json").read_text())
    assert stored["data"] == {"price": "9.95", "discount": None}

    product_again = store.get(product.qid)
    assert product_again.price == Decimal("9.95")
    assert isinstance(product_again.price, Decimal)
    assert product_again.discount is None


def test_put_failing_serialization_keeps_stored_object(tmp_path):
    store = Store(path=tmp_path, models=[Person])

    person = Person.create(name="John Smith")
    store.put(person)

    person.update(name={"not", "serializable"})
    with pytest.raises(TypeError):
        store.put(person)

    assert store.get(person.qid).name == "John Smith"
    assert [p.name for p in store.list(Person)] == ["John Smith"]
    assert sorted(f.name for f in (tmp_path / "Person").iterdir()) == [
        f"{person.id}.json",
        "number.enumerator",
    ]


def test_put_failing_write_keeps_stored_object(tmp_path, monkeypatch):
    store = Store(path=tmp_path, models=[Person])

    person = Person.create(name="John Smith")
    store.put(person)

    def failing_fsync(fd):
        raise OSError("No space left on device")

    monkeypatch.setattr("sjdbl.store.os.fsync", failing_fsync)
    person.update(name="Jane Smith")
    with pytest.raises(OSError):
        store.put(person)

    assert store.get(person.qid).name == "John Smith"
    assert sorted(f.name for f in (tmp_path / "Person").iterdir()) == [
        f"{person.id}.json",
        "number.enumerator",
    ]


def test_put_detects_concurrent_change(tmp_path):
    store = Store(path=tmp_path, models=[Person])

    person = Person.create(name="John Smith")
    store.put(person)

    first = store.get(person.qid)
    second = store.get(person.qid)

    first.update(name="Jane Smith")
    store.put(first)

    second.update(name="Joe Smith")
    with pytest.raises(HasChangedException):
        store.put(second)

    assert store.get(person.qid).name == "Jane Smith"

    first.update(name="Jane Doe")
    store.put(first)
    assert store.get(person.qid).name == "Jane Doe"


def test_put_with_conflict_writes_nothing(tmp_path):
    store = Store(path=tmp_path, models=[Person])

    john = Person.create(name="John Smith")
    jane = Person.create(name="Jane Smith")
    store.put(john, jane)

    stale_jane = store.get(jane.qid)
    jane.update(name="Jane Doe")
    store.put(jane)

    john.update(name="John Doe")
    stale_jane.update(name="Jane Roe")
    with pytest.raises(HasChangedException):
        store.put(john, stale_jane)

    assert store.get(john.qid).name == "John Smith"
    assert store.get(jane.qid).name == "Jane Doe"


def test_archive_changes_revision(tmp_path):
    store = Store(path=tmp_path, models=[Person])

    person = Person.create(name="John Smith")
    store.put(person)
    stale = store.get(person.qid)

    person.mark_archived(store)
    assert store.get(person.qid).is_archived is True
    assert store.get(person.qid).__rev__ != stale.__rev__

    with pytest.raises(HasChangedException):
        stale.mark_archived(store, archived=False)


def test_proxy_equality_and_hash(tmp_path):
    store = Store(path=tmp_path, models=[Person])

    parent = Person.create(name="John Smith")
    child = Person.create(name="Joe Smith", parent=parent)
    store.put(parent, child)

    proxy = store.get(child.qid).parent
    assert isinstance(proxy, Proxy)
    assert parent == proxy
    assert proxy == parent
    assert hash(parent) == hash(proxy)
    # comparing and hashing must not load the proxy
    assert isinstance(proxy, Proxy)


def test_proxy_dunder_lookup_does_not_load(tmp_path):
    store = Store(path=tmp_path, models=[Person])

    parent = Person.create(name="John Smith")
    child = Person.create(name="Joe Smith", parent=parent)
    store.put(parent, child)

    proxy = store.get(child.qid).parent
    assert not hasattr(proxy, "__html__")
    assert isinstance(proxy, Proxy)

    assert proxy.__id__ == parent.__id__
    assert isinstance(proxy, Person)


def test_dangling_reference(tmp_path):
    store = Store(path=tmp_path, models=[Person])

    parent = Person.create(name="John Smith")
    child = Person.create(name="Joe Smith", parent=parent)
    store.put(child)

    proxy = store.get(child.qid).parent
    assert not hasattr(proxy, "__html__")
    with pytest.raises(DanglingReferenceError):
        proxy.name


def test_deepcopy_with_proxy(tmp_path):
    store = Store(path=tmp_path, models=[Person])

    parent = Person.create(name="John Smith")
    child = Person.create(name="Joe Smith", parent=parent)
    store.put(parent, child)

    child_copy = copy.deepcopy(store.get(child.qid))
    assert child_copy.parent.store is store
    assert child_copy.parent.name == "John Smith"


def test_xml_none(tmp_path):
    class Doc(Base):
        FIELDS = [Field.xml("content")]

    store = Store(path=tmp_path, models=[Doc])

    doc = Doc()
    assert doc.content is None
    store.put(doc)
    assert store.get(doc.qid).content is None


def test_revision_changes_on_put_not_on_update(tmp_path):
    store = Store(path=tmp_path, models=[Person])

    person = Person.create(name="John Smith")
    rev = person.__rev__

    person.update(name="Jane Smith")
    assert person.__rev__ == rev

    store.put(person)
    assert person.__rev__ != rev
    assert store.get(person.qid).__rev__ == person.__rev__


def test_failed_put_keeps_revision(tmp_path, monkeypatch):
    store = Store(path=tmp_path, models=[Person])

    person = Person.create(name="John Smith")
    store.put(person)
    rev = person.__rev__

    def failing_fsync(fd):
        raise OSError("No space left on device")

    monkeypatch.setattr("sjdbl.store.os.fsync", failing_fsync)
    person.update(name="Jane Smith")
    with pytest.raises(OSError):
        store.put(person)
    assert person.__rev__ == rev

    monkeypatch.undo()
    store.put(person)
    assert store.get(person.qid).name == "Jane Smith"


def test_put_failing_serialization_writes_nothing(tmp_path):
    store = Store(path=tmp_path, models=[Person])

    john = Person.create(name="John Smith")
    jane = Person.create(name="Jane Smith")
    store.put(john, jane)

    john.update(name="John Doe")
    jane.update(name={"not", "serializable"})
    with pytest.raises(TypeError):
        store.put(john, jane)

    assert store.get(john.qid).name == "John Smith"


def test_concurrent_puts_of_same_version(tmp_path):
    store = Store(path=tmp_path, models=[Person])

    person = Person.create(name="John Smith")
    store.put(person)

    copies = [store.get(person.qid) for _ in range(8)]
    for i, copy_ in enumerate(copies):
        copy_.update(name=f"Name {i}")

    def put(obj):
        try:
            store.put(obj)
            return True
        except HasChangedException:
            return False

    with ThreadPoolExecutor(max_workers=8) as executor:
        results = list(executor.map(put, copies))

    assert results.count(True) == 1


def test_stored_file_is_indented(tmp_path):
    store = Store(path=tmp_path, models=[Person])

    person = Person.create(name="John Smith")
    store.put(person)

    lines = (tmp_path / "Person" / f"{person.id}.json").read_text().splitlines()
    assert lines[0] == "{"
    assert '    "name": "John Smith",' in lines


def test_archive_through_object_and_store(tmp_path):
    store = Store(path=tmp_path, models=[Person])

    john = Person.create(name="John Smith")
    jane = Person.create(name="Jane Smith")
    store.put(john, jane)

    john.archive(store)
    store.archive(jane)

    assert store.get(john.qid).is_archived is True
    assert store.get(jane.qid).is_archived is True


class Secret(Base):
    FIELDS = [Field.str("value")]


def test_qid_cannot_reach_other_files(tmp_path):
    store = Store(path=tmp_path / "data", models=[Person, Secret])
    secret = Secret.create(value="secret")
    store.put(secret)
    (tmp_path / "outside.json").write_text(
        json.dumps({"data": {"name": "outside"}, "meta": {}})
    )

    for qid in [
        f"Person:../Secret/{secret.id}",
        "Person:../../outside",
        "Person:..\\..\\outside",
        "Person:",
        "Person",
        "Unknown:abc",
        f"{secret.qid}:extra",
    ]:
        assert store.get(qid) is None, qid

    with pytest.raises(ValueError):
        store.delete("Person:../../outside")
    assert (tmp_path / "outside.json").exists()
    assert store.get(secret.qid).value == "secret"


def test_collection_default_is_not_shared():
    class Group(Base):
        FIELDS = [Field.collection("members")]

    first, second = Group.create(), Group.create()
    first.members.append(second)
    assert Group.create().members == []
    assert second.members == []


def test_enum_none(tmp_path):
    class Shirt(Base):
        FIELDS = [Field.enum("gender", GenderEnum, default=None)]

    store = Store(path=tmp_path, models=[Shirt])
    shirt = Shirt.create()
    store.put(shirt)
    assert store.get(shirt.qid).gender is None

    shirt.update(gender=GenderEnum.male)
    store.put(shirt)
    assert store.get(shirt.qid).gender is GenderEnum.male
