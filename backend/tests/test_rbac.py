"""Unit tests for the role-hierarchy logic in app.core.rbac."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

from app.core.rbac import (
    can_assign_role,
    can_bootstrap_own_workspace,
    guest_access_ttl,
    has_at_least,
    is_guest_access_expired,
)
from app.db.models import UserRole

ALL_ROLES = [UserRole.SUPER_ADMIN, UserRole.COMPANY_ADMIN, UserRole.MANAGER, UserRole.EMPLOYEE, UserRole.GUEST]


def test_user_role_rename_preserves_string_value():
    """Guards the ADMIN -> COMPANY_ADMIN rename: existing rows/JWTs carry 'admin'."""
    assert UserRole("admin") == UserRole.COMPANY_ADMIN
    assert UserRole.COMPANY_ADMIN.value == "admin"


def test_user_role_has_five_distinct_members():
    values = {role.value for role in ALL_ROLES}
    assert values == {"super_admin", "admin", "manager", "employee", "guest"}


def test_has_at_least_rank_ordering():
    # Higher-ranked roles satisfy lower-ranked minimums.
    assert has_at_least(UserRole.SUPER_ADMIN, UserRole.GUEST)
    assert has_at_least(UserRole.COMPANY_ADMIN, UserRole.MANAGER)
    assert has_at_least(UserRole.MANAGER, UserRole.EMPLOYEE)

    # Equal rank satisfies itself.
    for role in ALL_ROLES:
        assert has_at_least(role, role)

    # Lower-ranked roles do not satisfy a higher minimum.
    assert not has_at_least(UserRole.EMPLOYEE, UserRole.MANAGER)
    assert not has_at_least(UserRole.GUEST, UserRole.EMPLOYEE)
    assert not has_at_least(UserRole.MANAGER, UserRole.COMPANY_ADMIN)


def test_can_assign_role_own_rank_and_below():
    assert can_assign_role(UserRole.COMPANY_ADMIN, UserRole.COMPANY_ADMIN)
    assert can_assign_role(UserRole.COMPANY_ADMIN, UserRole.MANAGER)
    assert can_assign_role(UserRole.COMPANY_ADMIN, UserRole.GUEST)


def test_can_assign_role_rejects_above_own_rank():
    assert not can_assign_role(UserRole.COMPANY_ADMIN, UserRole.SUPER_ADMIN)
    assert not can_assign_role(UserRole.MANAGER, UserRole.COMPANY_ADMIN)
    assert not can_assign_role(UserRole.EMPLOYEE, UserRole.MANAGER)


def test_guest_access_ttl_unaffected_for_non_guests():
    default_ttl = timedelta(minutes=15)
    now = datetime.now(timezone.utc)
    soon = now + timedelta(minutes=1)
    for role in (UserRole.SUPER_ADMIN, UserRole.COMPANY_ADMIN, UserRole.MANAGER, UserRole.EMPLOYEE):
        assert guest_access_ttl(default_ttl, role, soon, now) == default_ttl


def test_guest_access_ttl_unaffected_when_no_expiry_set():
    default_ttl = timedelta(minutes=15)
    now = datetime.now(timezone.utc)
    assert guest_access_ttl(default_ttl, UserRole.GUEST, None, now) == default_ttl


def test_guest_access_ttl_clamps_to_nearer_expiry():
    default_ttl = timedelta(minutes=15)
    now = datetime.now(timezone.utc)
    expires_in_five = now + timedelta(minutes=5)
    assert guest_access_ttl(default_ttl, UserRole.GUEST, expires_in_five, now) == timedelta(minutes=5)


def test_guest_access_ttl_never_negative_for_past_expiry():
    default_ttl = timedelta(minutes=15)
    now = datetime.now(timezone.utc)
    already_expired = now - timedelta(minutes=1)
    assert guest_access_ttl(default_ttl, UserRole.GUEST, already_expired, now) == timedelta(0)


def test_is_guest_access_expired_true_after_expiry():
    now = datetime.now(timezone.utc)
    assert is_guest_access_expired(UserRole.GUEST, now - timedelta(seconds=1), now)


def test_is_guest_access_expired_false_before_expiry():
    now = datetime.now(timezone.utc)
    assert not is_guest_access_expired(UserRole.GUEST, now + timedelta(minutes=1), now)


def test_is_guest_access_expired_false_when_unset():
    now = datetime.now(timezone.utc)
    assert not is_guest_access_expired(UserRole.GUEST, None, now)


def test_is_guest_access_expired_always_false_for_non_guests():
    now = datetime.now(timezone.utc)
    past = now - timedelta(days=1)
    for role in (UserRole.SUPER_ADMIN, UserRole.COMPANY_ADMIN, UserRole.MANAGER, UserRole.EMPLOYEE):
        assert not is_guest_access_expired(role, past, now)


def test_can_bootstrap_own_workspace_allowed_when_sole_member():
    # Nothing is stranded by leaving an org you're the only member of, regardless of rank.
    for role in ALL_ROLES:
        assert can_bootstrap_own_workspace(role, org_member_count=1)


def test_can_bootstrap_own_workspace_allowed_for_non_admin_in_a_real_org():
    # The actual target scenario: an Employee/Manager/Guest stuck in someone else's
    # multi-member org can always leave to found their own — nobody they'd be
    # stranding, since they hold no admin responsibility there.
    for role in (UserRole.EMPLOYEE, UserRole.MANAGER, UserRole.GUEST):
        assert can_bootstrap_own_workspace(role, org_member_count=5)


def test_can_bootstrap_own_workspace_blocked_for_admin_of_a_real_org():
    # A Company Admin/Super Admin of a multi-member org would abandon it
    # without an admin — blocked; they should reassign another admin first.
    assert not can_bootstrap_own_workspace(UserRole.COMPANY_ADMIN, org_member_count=2)
    assert not can_bootstrap_own_workspace(UserRole.SUPER_ADMIN, org_member_count=10)
