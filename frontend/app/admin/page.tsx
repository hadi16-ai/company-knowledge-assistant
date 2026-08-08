"use client";

import { useCallback, useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import { toast } from "sonner";
import { X } from "lucide-react";
import { AppShell } from "@/components/layout/app-shell";
import { MemberRow } from "@/components/admin/member-row";
import { InviteMemberDialog } from "@/components/admin/invite-member-dialog";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Skeleton } from "@/components/ui/skeleton";
import { useAuth } from "@/lib/auth-context";
import { hasAtLeast, ROLE_LABELS } from "@/lib/roles";
import {
  ApiError,
  invitationsApi,
  usersApi,
  type Invitation,
  type OrgMember,
  type UpdateMemberRequest,
} from "@/lib/api";

export default function AdminPage() {
  const { user } = useAuth();
  const router = useRouter();
  const isAuthorized = hasAtLeast(user?.role, "admin");

  const [members, setMembers] = useState<OrgMember[]>([]);
  const [invitations, setInvitations] = useState<Invitation[]>([]);
  const [isLoading, setIsLoading] = useState(true);

  const refresh = useCallback(async () => {
    try {
      const [memberList, invitationList] = await Promise.all([usersApi.list(), invitationsApi.list()]);
      setMembers(memberList);
      setInvitations(invitationList);
    } catch (error) {
      if (error instanceof ApiError) toast.error(error.message);
    } finally {
      setIsLoading(false);
    }
  }, []);

  useEffect(() => {
    // AppShell withholds rendering until `user` resolves, and this page redirects
    // unauthorized users below — but this component's own effects still run on
    // mount regardless, so gate on being authorized before fetching admin data.
    if (!user || !isAuthorized) return;
    void Promise.resolve().then(refresh);
  }, [user, isAuthorized, refresh]);

  useEffect(() => {
    if (user && !isAuthorized) router.replace("/chat");
  }, [user, isAuthorized, router]);

  async function updateMember(member: OrgMember, patch: UpdateMemberRequest) {
    try {
      const updated = await usersApi.update(member.id, patch);
      setMembers((prev) => prev.map((m) => (m.id === updated.id ? updated : m)));
    } catch (error) {
      toast.error(error instanceof ApiError ? error.message : "Failed to update member.");
    }
  }

  async function handleRevokeInvitation(invitation: Invitation) {
    try {
      await invitationsApi.revoke(invitation.id);
      setInvitations((prev) => prev.filter((i) => i.id !== invitation.id));
      toast.success("Invitation revoked.");
    } catch (error) {
      toast.error(error instanceof ApiError ? error.message : "Failed to revoke invitation.");
    }
  }

  if (!user || !isAuthorized) {
    return (
      <AppShell>
        <div className="flex flex-1 items-center justify-center">
          <Skeleton className="h-8 w-48" />
        </div>
      </AppShell>
    );
  }

  return (
    <AppShell>
      <div className="flex flex-1 flex-col overflow-y-auto px-6 py-6">
        <header className="mb-6 flex items-center justify-between gap-4">
          <div>
            <h1 className="text-lg font-semibold">Admin</h1>
            <p className="text-sm text-muted-foreground">Manage members, roles, and invitations for {user.org_name}.</p>
          </div>
          <InviteMemberDialog actorRole={user.role} onCreated={refresh} />
        </header>

        <div className="mx-auto w-full max-w-3xl space-y-6">
          <Card>
            <CardHeader>
              <CardTitle className="text-sm font-medium">Members</CardTitle>
            </CardHeader>
            <CardContent className="p-0">
              {isLoading ? (
                <div className="space-y-3 p-4">
                  <Skeleton className="h-10 w-full" />
                  <Skeleton className="h-10 w-full" />
                </div>
              ) : members.length === 0 ? (
                <p className="p-4 text-sm text-muted-foreground">No members found.</p>
              ) : (
                members.map((member) => (
                  <MemberRow
                    key={member.id}
                    member={member}
                    actorRole={user.role}
                    isSelf={member.id === user.id}
                    onChangeRole={(target, role) => updateMember(target, { role })}
                    onToggleActive={(target) => updateMember(target, { is_active: !target.is_active })}
                    onSetExpiry={(target, expiresAt) => updateMember(target, { expires_at: expiresAt })}
                  />
                ))
              )}
            </CardContent>
          </Card>

          <Card>
            <CardHeader>
              <CardTitle className="text-sm font-medium">Pending invitations</CardTitle>
            </CardHeader>
            <CardContent className="p-0">
              {isLoading ? (
                <div className="space-y-3 p-4">
                  <Skeleton className="h-10 w-full" />
                </div>
              ) : invitations.length === 0 ? (
                <p className="p-4 text-sm text-muted-foreground">No pending invitations.</p>
              ) : (
                invitations.map((invitation) => (
                  <div
                    key={invitation.id}
                    className="flex items-center justify-between gap-4 border-b px-4 py-3 last:border-b-0"
                  >
                    <div className="min-w-0">
                      <p className="text-sm font-medium">{ROLE_LABELS[invitation.role]}</p>
                      <p className="truncate text-xs text-muted-foreground">
                        {invitation.email_hint ?? "Anyone with the link"} · expires{" "}
                        {new Date(invitation.expires_at).toLocaleDateString()}
                      </p>
                    </div>
                    <Button
                      variant="ghost"
                      size="icon"
                      aria-label="Revoke invitation"
                      onClick={() => handleRevokeInvitation(invitation)}
                    >
                      <X className="h-4 w-4" />
                    </Button>
                  </div>
                ))
              )}
            </CardContent>
          </Card>
        </div>
      </div>
    </AppShell>
  );
}
