"""Tests for marketplace bootstrap on startup."""
from __future__ import annotations
from app.services.marketplace_service import MarketplaceService

_SYSTEM_USER = "00000000-0000-0000-0000-000000000001"


def test_bootstrap_default_when_empty(db):
    """Empty marketplace_registry → default registered."""
    from app.models.marketplace import MarketplaceRegistry
    db.query(MarketplaceRegistry).delete()
    db.commit()
    svc = MarketplaceService(db)
    svc.bootstrap_default_marketplace(_SYSTEM_USER)
    rows = db.query(MarketplaceRegistry).all()
    assert len(rows) == 1
    assert rows[0].name == "anthropics/claude-plugins-official"


def test_bootstrap_registers_when_default_absent(db):
    """Non-empty table but default missing → default still gets registered."""
    from app.models.marketplace import MarketplaceRegistry
    db.query(MarketplaceRegistry).delete()
    db.add(MarketplaceRegistry(name="user/custom", url="https://example.test/x", created_by=_SYSTEM_USER))
    db.commit()
    svc = MarketplaceService(db)
    svc.bootstrap_default_marketplace(_SYSTEM_USER)
    rows = db.query(MarketplaceRegistry).all()
    assert len(rows) == 2
    names = {r.name for r in rows}
    assert "anthropics/claude-plugins-official" in names


def test_bootstrap_skipped_when_default_exists(db):
    """Default already present → idempotent, no duplicate."""
    from app.models.marketplace import MarketplaceRegistry
    db.query(MarketplaceRegistry).delete()
    db.add(MarketplaceRegistry(
        name="anthropics/claude-plugins-official",
        url="https://github.com/anthropics/claude-plugins-official",
        created_by=_SYSTEM_USER,
    ))
    db.commit()
    svc = MarketplaceService(db)
    svc.bootstrap_default_marketplace(_SYSTEM_USER)
    rows = db.query(MarketplaceRegistry).all()
    assert len(rows) == 1
