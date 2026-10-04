from unittest.mock import patch
from uuid import UUID, uuid4

import pytest
from fastapi import HTTPException
from sqlalchemy import create_engine, event
from sqlalchemy.orm import Session

from app.db.base import Base
from app.domain.investigation import InputType
from app.modules.investigations.models import MediaAsset
from app.modules.investigations.routes import get_investigation_media_preview
from app.modules.investigations.service import InvestigationService


@pytest.fixture
def preview_context():
    engine = create_engine("sqlite+pysqlite:///:memory:")
    event.listen(
        engine,
        "connect",
        lambda connection, _: connection.execute("PRAGMA foreign_keys=ON"),
    )
    Base.metadata.create_all(engine)
    session = Session(engine, expire_on_commit=False)
    investigation = InvestigationService(session).create(
        owner_id=UUID("00000000-0000-4000-8000-000000000001"),
        content="Inspect this image",
        input_type=InputType.IMAGE,
        idempotency_key=f"preview-{uuid4()}",
    )
    original = MediaAsset(
        investigation_id=investigation.id,
        asset_role="ORIGINAL",
        storage_key="private/original-key",
        media_type="IMAGE",
        mime_type="image/jpeg",
        size_bytes=900,
        sha256="a" * 64,
        metadata_json={"original_filename": "private.jpg"},
    )
    session.add(original)
    session.flush()
    derivative = MediaAsset(
        investigation_id=investigation.id,
        parent_asset_id=original.id,
        asset_role="DERIVED",
        artifact_type="NORMALIZED_IMAGE",
        transformation_version="image-normalization-v1",
        storage_key="private-derived/normalized-key",
        media_type="IMAGE",
        mime_type="image/png",
        size_bytes=300,
        sha256="b" * 64,
        metadata_json={},
    )
    session.add(derivative)
    session.commit()
    try:
        yield session, investigation
    finally:
        session.close()
        engine.dispose()


def test_preview_serves_only_normalized_private_derivative(preview_context):
    session, investigation = preview_context
    normalized_bytes = b"metadata-stripped-image"
    with patch(
        "app.modules.investigations.routes.get_private_object",
        return_value=normalized_bytes,
    ) as load:
        response = get_investigation_media_preview(investigation.id, session)
    assert response.body == normalized_bytes
    assert response.media_type == "image/png"
    assert response.headers["cache-control"] == "private, no-store"
    assert response.headers["x-content-type-options"] == "nosniff"
    load.assert_called_once_with(key="private-derived/normalized-key")
    assert "private/original-key" not in response.headers.values()


def test_preview_is_unavailable_until_safe_derivative_exists(preview_context):
    session, investigation = preview_context
    derivative = session.query(MediaAsset).filter_by(artifact_type="NORMALIZED_IMAGE").one()
    session.delete(derivative)
    session.commit()
    with pytest.raises(HTTPException) as error:
        get_investigation_media_preview(investigation.id, session)
    assert error.value.status_code == 404
