"""Where generated audio (and later images) is stored for good.

Files are named by the hash of their bytes (`hashed_path`), so a stored file
never changes: the same bytes give the same name, different bytes a new one.
That is why the Cloud Storage uploads may be create-only, the only permission
the API's service account has on the bucket.

Which storage is used (`STORAGE`):
- `MEDIA_BUCKET` set: that Cloud Storage bucket (production; local
  development can use it too).
- otherwise, with mocks on: a local folder the app serves under /media (local
  development and tests; tests replace it with a fake).
- otherwise: none. The settings refuse to start with audio on and no bucket.
"""

import asyncio
import hashlib
from abc import ABC, abstractmethod
from pathlib import Path
from urllib.parse import quote

from google.api_core import exceptions as google_exceptions
from google.auth import exceptions as auth_exceptions
from google.cloud import storage

from settings import settings

# The repository's own local-media/ folder (gitignored), served by main.py at
# LOCAL_MEDIA_URL: port 8000 is where the Vite dev proxy sends /api.
LOCAL_MEDIA_DIR = Path(__file__).resolve().parents[1] / "local-media"
LOCAL_MEDIA_URL = "http://localhost:8000/media"


class StorageError(Exception):
    """The file could not be stored. The message is safe to log and show."""


def hashed_path(folder: str, data: bytes, extension: str) -> str:
    """`<folder>/<sha256 of data>.<extension>`, e.g. `audio/en/google/3f2a….mp3`."""
    return f"{folder}/{hashlib.sha256(data).hexdigest()}.{extension}"


class MediaStorage(ABC):
    @abstractmethod
    async def upload(self, data: bytes, path: str, content_type: str) -> str:
        """Store `data` at `path` and return its public URL.

        If `path` already exists it is left as it is: paths come from
        `hashed_path`, so it already holds these bytes.

        Raises:
            StorageError: the file could not be stored.
        """


class CloudStorage(MediaStorage):
    """A public-read Cloud Storage bucket; uploads are create-only."""

    # Stored files never change (their name is their hash), so browsers and
    # Google's cache may keep them for a year.
    CACHE_CONTROL = "public, max-age=31536000, immutable"
    TIMEOUT_SECONDS = 30

    def __init__(self, bucket_name: str, client: storage.Client | None = None):
        self.bucket_name = bucket_name
        # Created on first upload, so importing the app needs no credentials.
        self._client = client

    async def upload(self, data: bytes, path: str, content_type: str) -> str:
        # The library is blocking: run it in a thread, off the event loop.
        await asyncio.to_thread(self._upload, data, path, content_type)
        return self.url(path)

    def url(self, path: str) -> str:
        return f"https://storage.googleapis.com/{self.bucket_name}/{quote(path)}"

    def _upload(self, data: bytes, path: str, content_type: str) -> None:
        try:
            if self._client is None:
                self._client = storage.Client()
            blob = self._client.bucket(self.bucket_name).blob(path)
            blob.cache_control = self.CACHE_CONTROL
            # Generation 0 means "only if no file has this name yet", so the
            # service account never needs permission to overwrite or delete.
            blob.upload_from_string(
                data, content_type=content_type, if_generation_match=0, timeout=self.TIMEOUT_SECONDS
            )
        except google_exceptions.PreconditionFailed:
            pass  # already stored: same name, same bytes
        except (google_exceptions.GoogleAPIError, auth_exceptions.GoogleAuthError) as error:
            raise StorageError(f"Cloud Storage upload failed: {type(error).__name__}") from error


class LocalFolderStorage(MediaStorage):
    """Files in a local folder, served by the app (local development only)."""

    def __init__(self, folder: Path = LOCAL_MEDIA_DIR, base_url: str = LOCAL_MEDIA_URL):
        self.folder = folder
        self.base_url = base_url

    async def upload(self, data: bytes, path: str, content_type: str) -> str:
        await asyncio.to_thread(self._write, data, path)
        return f"{self.base_url}/{quote(path)}"

    def _write(self, data: bytes, path: str) -> None:
        target = (self.folder / path).resolve()
        if not target.is_relative_to(self.folder.resolve()):
            raise StorageError(f"Path outside the media folder: {path}")
        if target.exists():
            return
        try:
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(data)
        except OSError as error:
            raise StorageError(f"Could not write {path}: {type(error).__name__}") from error


def build_storage() -> MediaStorage | None:
    if settings.media_bucket:
        return CloudStorage(settings.media_bucket)
    if settings.use_mocks:
        return LocalFolderStorage()
    return None


STORAGE = build_storage()
