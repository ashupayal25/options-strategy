import pytest

from otm_strategy import positions
from otm_strategy.storage import LocalStore, S3Store, make_store


class NoSuchKey(Exception):
    response = {"Error": {"Code": "NoSuchKey"}}


class FakeS3:
    def __init__(self):
        self.objects = {}

    def put_object(self, Bucket, Key, Body, ContentType):
        self.objects[(Bucket, Key)] = Body

    def get_object(self, Bucket, Key):
        if (Bucket, Key) not in self.objects:
            raise NoSuchKey()
        body = self.objects[(Bucket, Key)]
        return {"Body": type("B", (), {"read": lambda self_: body})()}


def test_local_store_roundtrip_and_missing(tmp_path):
    s = LocalStore(tmp_path)
    assert s.read_text("a/b.txt") is None
    s.write_text("a/b.txt", "hello")
    assert s.read_text("a/b.txt") == "hello"


def test_s3_store_roundtrip_missing_and_prefix():
    fake = FakeS3()
    s = S3Store("bucket", "otm/", client=fake)
    assert s.read_text("positions.json") is None
    s.write_text("positions.json", "[]")
    assert ("bucket", "otm/positions.json") in fake.objects
    assert s.read_text("positions.json") == "[]"
    assert s.describe("x") == "s3://bucket/otm/x"


def test_s3_other_errors_are_raised():
    class Denied(Exception):
        response = {"Error": {"Code": "AccessDenied"}}

    class C:
        def get_object(self, **kw):
            raise Denied()

    with pytest.raises(Denied):
        S3Store("b", client=C()).read_text("k")


def test_make_store_variants(tmp_path, monkeypatch):
    monkeypatch.delenv("OTM_STORE", raising=False)
    assert isinstance(make_store(str(tmp_path)), LocalStore)
    s3 = make_store("s3://my-bucket/otm/")
    assert isinstance(s3, S3Store) and s3.bucket == "my-bucket" and s3.prefix == "otm"
    monkeypatch.setenv("OTM_STORE", str(tmp_path))
    assert make_store().root == tmp_path


def test_positions_record_close(tmp_path):
    s = LocalStore(tmp_path)
    assert positions.load(s) == []
    a = positions.record(s, "PE", 24750, 24250, "2026-11-24", 2, "2026-11-18")
    b = positions.record(s, "CE", 26100, 26650, "2026-11-24", 2, "2026-11-18")
    assert (a, b) == (1, 2)
    assert positions.close(s, 1) == 1
    assert [r["id"] for r in positions.load(s)] == [2]
    assert positions.record(s, "PE", 1, 2, "2026-12-01", 1) == 3
