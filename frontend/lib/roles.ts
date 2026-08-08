export type UserRole = "super_admin" | "admin" | "manager" | "employee" | "guest";

// Mirrors backend/app/core/rbac.py::ROLE_RANK. "admin" is the DB/JWT string
// value for what the UI calls "Company Admin" (see ROLE_LABELS) — kept from
// the original two-role model so existing accounts/tokens stay valid.
export const ROLE_RANK: Record<UserRole, number> = {
  super_admin: 4,
  admin: 3,
  manager: 2,
  employee: 1,
  guest: 0,
};

export const ROLE_LABELS: Record<UserRole, string> = {
  super_admin: "Super Admin",
  admin: "Company Admin",
  manager: "Manager",
  employee: "Employee",
  guest: "Guest",
};

export const ASSIGNABLE_ROLES: UserRole[] = ["admin", "manager", "employee", "guest"];

/** True if `role` outranks or equals `minimum`. UX convenience only — the backend is the real boundary. */
export function hasAtLeast(role: UserRole | null | undefined, minimum: UserRole): boolean {
  if (!role) return false;
  return ROLE_RANK[role] >= ROLE_RANK[minimum];
}

/** True if `actorRole` is allowed to assign `targetRole` (own rank or below). */
export function canAssignRole(actorRole: UserRole | null | undefined, targetRole: UserRole): boolean {
  if (!actorRole) return false;
  return ROLE_RANK[actorRole] >= ROLE_RANK[targetRole];
}
