"""Tests for POST /skills/install with source='marketplace' + marketplace_id + plugin_name.

Verifies the fix: marketplace install path calls MarketplaceService.install_plugin()
instead of raising 400 "content_base64 为必填".
"""
from __future__ import annotations

import uuid
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.schemas.marketplace import InstallReport
from app.services.skill_install_service import SkillInstallService


# ---------------------------------------------------------------------------
# Unit tests for SkillInstallService — marketplace_id forwarded to DB
# ---------------------------------------------------------------------------


def test_install_with_marketplace_id_persists_to_db(db):
    """install() with marketplace_id stores it on the skill_installs row."""
    from app.models.user import User

    user = User(
        email=f"mp-{uuid.uuid4()}@test.local",
        username=f"mpuser{uuid.uuid4().hex[:8]}",
        password_hash="x",
        role="user",
    )
    db.add(user)
    db.flush()

    svc = SkillInstallService(db=db)
    record = svc.install(
        user_id=user.id,
        skill_name="git-tool",
        source="marketplace",
        source_url="https://example.test/mp.json",
        version="1.0.0",
        install_path="/app/data/plugin_cache/test-mp/git-tool/1.0.0/skills/git-tool",
        has_hooks=False,
        has_mcp=False,
        marketplace_id="mp-uuid-123",
    )
    assert record.skill_name == "git-tool"
    assert record.source == "marketplace"
    assert record.marketplace_id == "mp-uuid-123"


# ---------------------------------------------------------------------------
# Integration test: install endpoint delegates to MarketplaceService.install_plugin
# when source='marketplace' + marketplace_id + plugin_name, no content_base64
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_install_endpoint_calls_marketplace_install_plugin(db):
    """When POST /skills/install {source='marketplace', marketplace_id, plugin_name},
    the endpoint must call MarketplaceService.install_plugin (not raise 400).
    """
    from app.api.v1.skills import install_skill
    from app.api.v1.skills import SkillInstallRequest
    from app.models.user import User
    from app.models.skill_install import SkillInstall

    user = User(
        email=f"mp2-{uuid.uuid4()}@test.local",
        username=f"mp2user{uuid.uuid4().hex[:8]}",
        password_hash="x",
        role="user",
    )
    db.add(user)
    db.flush()

    # Pre-seed the skill_installs row that install_plugin() would write
    now = datetime.now(timezone.utc)
    si = SkillInstall(
        user_id=user.id,
        skill_name="git-tool",
        source="marketplace",
        source_url="https://example.test/mp.json",
        version="1.0.0",
        installed_at=now,
        updated_at=now,
        metadata_={"install_path": "/tmp/git-tool", "has_hooks": False, "has_mcp": False, "status": "installed"},
        marketplace_id="mp-uuid-456",
    )
    db.add(si)
    db.commit()

    fake_report = InstallReport(
        plugin_name="git-tool",
        installed_skills=["git-tool"],
        failures=[],
    )

    request = SkillInstallRequest(
        skill_name=None,
        source="marketplace",
        marketplace_id="mp-uuid-456",
        plugin_name="git-tool",
    )

    with patch(
        "app.api.v1.skills.MarketplaceService",
    ) as MockMpSvc:
        mock_instance = MagicMock()
        mock_instance.install_plugin = AsyncMock(return_value=fake_report)
        MockMpSvc.return_value = mock_instance

        with patch("app.api.v1.skills._get_redis_client", return_value=None):
            response = await install_skill(
                request=request,
                db=db,
                current_user=user,
            )

    mock_instance.install_plugin.assert_called_once_with(
        marketplace_id="mp-uuid-456",
        plugin_name="git-tool",
        user_id=str(user.id),
    )
    assert response.data.skill_name == "git-tool"
    assert response.data.marketplace_id == "mp-uuid-456"
