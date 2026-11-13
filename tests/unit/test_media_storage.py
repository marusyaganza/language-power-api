# tests/unit/test_media_storage.py
"""Storing generated files: names, Cloud Storage (with a fake client), the local folder."""

import hashlib

import pytest
from google.api_core import exceptions as google_exceptions

import core.media_storage
from core.media_storage import CloudStorage, LocalFolderStorage, StorageError, build_storage, hashed_path
from settings import settings

pytestmark = pytest.mark.anyio


@pytest.fixture
def anyio_backend():
    return "asyncio"


class FakeBlob:
    def __init__(self, client, path):
        self.client, self.path, self.cache_control = client, path, None

    def upload_from_string(self, data, **kwargs):
        self.client.uploads.append({"path": self.path, "data": data, "cache_control": self.cache_control, **kwargs})
        if self.client.error:
            raise self.client.error


class FakeClient:
    """Stands in for storage.Client: records uploads, or raises `error`."""

    def __init__(self, error=None):
        self.error, self.uploads, self.buckets = error, [], []

    def bucket(self, name):
        self.buckets.append(name)
        return self

    def blob(self, path):
        return FakeBlob(self, path)


def test_a_hashed_path_is_named_by_the_bytes():
    path = hashed_path("audio/ko/google", b"mp3", "mp3")

    assert path == f"audio/ko/google/{hashlib.sha256(b'mp3').hexdigest()}.mp3"
    assert hashed_path("audio/ko/google", b"mp3", "mp3") == path
    assert hashed_path("audio/ko/google", b"other", "mp3") != path


# --------------------------------------------------------------------------- #
# Cloud Storage, with a fake client
# --------------------------------------------------------------------------- #


async def test_cloud_uploads_are_create_only_and_cached_for_good():
    client = FakeClient()

    url = await CloudStorage("media-bucket", client).upload(b"mp3", "audio/en/google/abc.mp3", "audio/mpeg")

    assert url == "https://storage.googleapis.com/media-bucket/audio/en/google/abc.mp3"
    assert client.buckets == ["media-bucket"]
    [upload] = client.uploads
    assert upload["data"] == b"mp3"
    assert upload["content_type"] == "audio/mpeg"
    assert upload["if_generation_match"] == 0
    assert upload["cache_control"] == "public, max-age=31536000, immutable"


async def test_a_file_already_stored_is_not_an_error():
    client = FakeClient(error=google_exceptions.PreconditionFailed("exists"))

    url = await CloudStorage("media-bucket", client).upload(b"mp3", "audio/en/google/abc.mp3", "audio/mpeg")

    assert url == "https://storage.googleapis.com/media-bucket/audio/en/google/abc.mp3"


@pytest.mark.parametrize(
    "error", [google_exceptions.Forbidden("no permission"), google_exceptions.ServiceUnavailable("down")]
)
async def test_cloud_errors_become_storage_errors(error):
    with pytest.raises(StorageError):
        await CloudStorage("media-bucket", FakeClient(error=error)).upload(b"mp3", "a.mp3", "audio/mpeg")


def test_cloud_urls_are_escaped():
    assert CloudStorage("b").url("audio/x y.mp3") == "https://storage.googleapis.com/b/audio/x%20y.mp3"


def test_making_cloud_storage_needs_no_credentials():
    assert CloudStorage("media-bucket")._client is None


# --------------------------------------------------------------------------- #
# The local folder
# --------------------------------------------------------------------------- #


async def test_the_local_folder_writes_the_file_and_returns_its_url(tmp_path):
    storage = LocalFolderStorage(tmp_path, "http://localhost:8000/media")

    url = await storage.upload(b"mp3", "audio/en/google/abc.mp3", "audio/mpeg")

    assert url == "http://localhost:8000/media/audio/en/google/abc.mp3"
    assert (tmp_path / "audio/en/google/abc.mp3").read_bytes() == b"mp3"


async def test_the_local_folder_never_replaces_a_file(tmp_path):
    storage = LocalFolderStorage(tmp_path, "http://localhost:8000/media")
    await storage.upload(b"first", "a.mp3", "audio/mpeg")

    await storage.upload(b"second", "a.mp3", "audio/mpeg")

    assert (tmp_path / "a.mp3").read_bytes() == b"first"


async def test_the_local_folder_refuses_paths_outside_it(tmp_path):
    storage = LocalFolderStorage(tmp_path / "media", "http://localhost:8000/media")

    with pytest.raises(StorageError):
        await storage.upload(b"mp3", "../outside.mp3", "audio/mpeg")
    assert not (tmp_path / "outside.mp3").exists()


# --------------------------------------------------------------------------- #
# Which storage
# --------------------------------------------------------------------------- #


def test_a_bucket_means_cloud_storage(monkeypatch):
    monkeypatch.setattr(settings, "media_bucket", "media-bucket")

    storage = build_storage()

    assert isinstance(storage, CloudStorage) and storage.bucket_name == "media-bucket"


def test_mocks_without_a_bucket_mean_the_local_folder(monkeypatch):
    monkeypatch.setattr(settings, "media_bucket", "")
    monkeypatch.setattr(settings, "use_mocks", True)

    assert isinstance(build_storage(), LocalFolderStorage)


def test_no_bucket_and_no_mocks_means_no_storage(monkeypatch):
    monkeypatch.setattr(settings, "media_bucket", "")
    monkeypatch.setattr(settings, "use_mocks", False)

    assert build_storage() is None


def test_tests_never_use_a_bucket():
    assert isinstance(core.media_storage.STORAGE, LocalFolderStorage)
