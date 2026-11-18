"""app/photos.py, with the storage client mocked. That no client is built at
import is checked in tests/test_db.py, with the connector."""

from unittest import mock
from uuid import uuid4

import pytest
from google.cloud.storage.retry import DEFAULT_RETRY

from app import photos

BUCKET = "zz-project-photos"
DATA = b"\xff\xd8 invented bytes, not a photo"


@pytest.fixture
def client(monkeypatch):
    monkeypatch.setenv("PHOTO_BUCKET", BUCKET)
    photos._storage.cache_clear()
    with mock.patch.object(photos.storage, "Client") as cls:
        yield cls
    photos._storage.cache_clear()


def test_store_photo_creates_the_object_with_explicit_settings(client):
    item_id = uuid4()
    photos.store_photo(item_id, DATA, "image/png")

    client.assert_called_once_with()
    client.return_value.bucket.assert_called_once_with(BUCKET)
    client.return_value.get_bucket.assert_not_called()
    bucket = client.return_value.bucket.return_value
    bucket.blob.assert_called_once_with(str(item_id))

    upload = bucket.blob.return_value.upload_from_string
    upload.assert_called_once()
    (data,), kwargs = upload.call_args
    assert data is DATA
    retry = kwargs.pop("retry")
    assert kwargs == {
        "content_type": "image/png",
        "if_generation_match": 0,
        "timeout": photos.UPLOAD_TIMEOUT_S,
    }
    assert retry.timeout == photos.RETRY_DEADLINE_S
    assert retry._predicate is DEFAULT_RETRY._predicate


def test_the_client_is_built_once(client):
    photos.store_photo(uuid4(), DATA, "image/jpeg")
    photos.store_photo(uuid4(), DATA, "image/jpeg")
    client.assert_called_once_with()
