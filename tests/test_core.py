import hashlib

import pytest

from traceable_rag.config import Settings
from traceable_rag.domain import SourceLocation
from traceable_rag.utils import sha256, stable_document_id


def test_identity() -> None:
    assert sha256(b"abc") == hashlib.sha256(b"abc").hexdigest()
    assert stable_document_id(b"abc") == stable_document_id(b"abc")
    assert stable_document_id(b"abc") != stable_document_id(b"abcd")


def test_settings_and_location() -> None:
    with pytest.raises(ValueError):
        Settings(chunk_size=100, chunk_overlap=100, _env_file=None)
    assert SourceLocation(sheet_name="价格", cell_range="A1:C5").page_number is None
