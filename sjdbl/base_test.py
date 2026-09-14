from .base import Base, Field


def test_update():
    class Some_Object(Base):
        FIELDS = [Field.str("name")]

    so = Some_Object()
    assert so.update() is False

    assert so.update(name="name") is True
    assert so.update(name="name") is False
    assert so.update(name="another name") is True
