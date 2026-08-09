"""Pure role-hierarchy logic: rank comparisons, assignment rules, guest expiry.

Kept free of FastAPI/DB dependencies (like ``app.core.security``) so it's
unit-testable in isolation — see ``tests/test_rbac.py``. ``app.deps`` wires
these into FastAPI dependencies; ``app.api.v1.auth`` uses the guest-TTL
helpers when issuing tokens.
"""

from __future__ import annotations

from datetime import datetime, timedelta

from app.db.models import UserRole

# Highest first. GUEST is intentionally rank 0 (lowest), not just "no admin
# rights" — it's a distinct, more restricted tier than EMPLOYEE.
ROLE_RANK: dict[UserRole, int] = {
    UserRole.SUPER_ADMIN: 4,
    UserRole.COMPANY_ADMIN: 3,
    UserRole.MANAGER: 2,
    UserRole.EMPLOYEE: 1,
    UserRole.GUEST: 0,
}


def has_at_least(role: UserRole, minimum: UserRole) -> bool:
    """True if `role` outranks or equals `minimum` in the hierarchy."""
    return ROLE_RANK[role] >= ROLE_RANK[minimum]


def can_assign_role(actor_role: UserRole, target_role: UserRole) -> bool:
    """True if `actor_role` is allowed to grant `target_role` to someone else.

    An actor may assign their own rank or below, never above — so a Company
    Admin can create peer admins but never a Super Admin. This is the only
    guard against privilege escalation via role assignment; there is no way
    to grant SUPER_ADMIN through the API at all in this slice (by design).
    """
    return ROLE_RANK[actor_role] >= ROLE_RANK[target_role]


def guest_access_ttl(default_ttl: timedelta, role: UserRole, expires_at: datetime | None, now: datetime) -> timedelta:
    """Clamp an access token's TTL to a guest's `expires_at`, if sooner.

    Access tokens are self-contained JWTs that are never re-checked against
    the DB mid-lifetime, so without this a guest whose `expires_at` passes
    partway through a token's life would keep working until that token's
    normal expiry. Non-guests, or guests with no `expires_at` set, get the
    default TTL unchanged. Never returns a negative duration — callers should
    reject the request outright first via `is_guest_access_expired`.
    """
    if role != UserRole.GUEST or expires_at is None:
        return default_ttl
    remaining = expires_at - now
    if remaining <= timedelta(0):
        return timedelta(0)
    return min(default_ttl, remaining)


def is_guest_access_expired(role: UserRole, expires_at: datetime | None, now: datetime) -> bool:
    """True if a guest's time-limited access has already passed."""
    if role != UserRole.GUEST or expires_at is None:
        return False
    return now >= expires_at


def can_bootstrap_own_workspace(role: UserRole, org_member_count: int) -> bool:
    """True if this account may found a brand-new org and move itself there as Company Admin.

    This is not self-promotion within the current org (never allowed) — it's
    detaching from the current org entirely, which is only unsafe when the
    account is the thing holding a real, multi-member org together. An
    account below Company Admin can always leave (there's nothing for them
    to strand); a Company Admin/Super Admin can only leave a org they're the
    sole member of — otherwise they'd abandon their org without an admin,
    and should reassign another admin via the existing admin panel first.
    """
    return org_member_count <= 1 or not has_at_least(role, UserRole.COMPANY_ADMIN)
