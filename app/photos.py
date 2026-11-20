"""The trial's photo store: one Cloud Storage object per item."""

import os
from functools import cache
from uuid import UUID

from google.cloud import storage
from google.cloud.storage.retry import DEFAULT_RETRY

# One attempt at one upload of at most 7.5MB, Cloud Run to a same-region
# bucket: normally a second or two, so an attempt still going after this is hung.
UPLOAD_TIMEOUT_S = 20
# All attempts together, so a transient error gets a retry or two; with the
# read's ~600s worst case it stays well under Cloud Run's 900s.
RETRY_DEADLINE_S = 45


@cache
def _storage() -> storage.Client:
    """Built on first use, never at import: building it looks up credentials,
    and the image must start with no configuration."""
    return storage.Client()


def store_photo(item_id: UUID, data: bytes, media_type: str) -> None:
    """Create the item's object, never overwrite one.

    bucket(), not get_bucket(): the runtime account can create objects but not
    read bucket metadata.
    """
    blob = _storage().bucket(os.environ["PHOTO_BUCKET"]).blob(str(item_id))
    blob.upload_from_string(
        data,
        content_type=media_type,
        if_generation_match=0,
        timeout=UPLOAD_TIMEOUT_S,
        retry=DEFAULT_RETRY.with_timeout(RETRY_DEADLINE_S),
    )
