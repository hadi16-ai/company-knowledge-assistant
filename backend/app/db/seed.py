"""Seed the single default organization Phase 1 (pre-multi-tenancy) runs under."""

from __future__ import annotations

import uuid

from sqlalchemy.orm import Session

from app.db.models import Organization

DEFAULT_ORG_SLUG = "default"
DEFAULT_ORG_NAME = "Default Organization"


def ensure_default_organization(db: Session) -> Organization:
    """Return the default organization, creating it if it doesn't exist yet."""
    org = db.query(Organization).filter(Organization.slug == DEFAULT_ORG_SLUG).one_or_none()
    if org is not None:
        return org

    org = Organization(id=uuid.uuid4(), name=DEFAULT_ORG_NAME, slug=DEFAULT_ORG_SLUG, plan="free")
    db.add(org)
    db.commit()
    db.refresh(org)
    return org
