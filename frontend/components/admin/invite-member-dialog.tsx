"use client";

import { useState } from "react";
import { toast } from "sonner";
import { Check, Copy, Loader2, UserPlus } from "lucide-react";
import type { UserRole } from "@/lib/api";
import { ASSIGNABLE_ROLES, ROLE_LABELS, canAssignRole } from "@/lib/roles";
import { ApiError, invitationsApi } from "@/lib/api";
import { Button, buttonVariants } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { DropdownMenu, DropdownMenuContent, DropdownMenuItem, DropdownMenuTrigger } from "@/components/ui/dropdown-menu";

const EXPIRY_OPTIONS = [
  { label: "1 day", hours: 24 },
  { label: "7 days", hours: 24 * 7 },
  { label: "30 days", hours: 24 * 30 },
];

export function InviteMemberDialog({
  actorRole,
  onCreated,
}: {
  actorRole: UserRole;
  onCreated: () => void;
}) {
  const [isOpen, setIsOpen] = useState(false);
  const [role, setRole] = useState<UserRole>("employee");
  const [emailHint, setEmailHint] = useState("");
  const [expiresInHours, setExpiresInHours] = useState(EXPIRY_OPTIONS[1].hours);
  const [isSubmitting, setIsSubmitting] = useState(false);
  const [inviteUrl, setInviteUrl] = useState<string | null>(null);
  const [copied, setCopied] = useState(false);

  function reset() {
    setRole("employee");
    setEmailHint("");
    setExpiresInHours(EXPIRY_OPTIONS[1].hours);
    setInviteUrl(null);
    setCopied(false);
  }

  async function handleCreate() {
    setIsSubmitting(true);
    try {
      const created = await invitationsApi.create({
        role,
        email_hint: emailHint || undefined,
        expires_in_hours: expiresInHours,
      });
      setInviteUrl(`${window.location.origin}/register?invite=${created.token}`);
      onCreated();
    } catch (error) {
      toast.error(error instanceof ApiError ? error.message : "Failed to create invite.");
    } finally {
      setIsSubmitting(false);
    }
  }

  async function handleCopy() {
    if (!inviteUrl) return;
    await navigator.clipboard.writeText(inviteUrl);
    setCopied(true);
    setTimeout(() => setCopied(false), 2000);
  }

  return (
    <>
      <Button onClick={() => setIsOpen(true)}>
        <UserPlus className="h-4 w-4" />
        Invite member
      </Button>
      <Dialog
        open={isOpen}
        onOpenChange={(open) => {
          setIsOpen(open);
          if (!open) reset();
        }}
      >
        <DialogContent>
        <DialogHeader>
          <DialogTitle>Invite a member</DialogTitle>
          <DialogDescription>
            {inviteUrl
              ? "Share this link — it can be used once."
              : "Generates a single-use link to join this workspace at the chosen role."}
          </DialogDescription>
        </DialogHeader>

        {inviteUrl ? (
          <div className="flex items-center gap-2">
            <Input readOnly value={inviteUrl} className="font-mono text-xs" />
            <Button type="button" variant="outline" size="icon" onClick={handleCopy} aria-label="Copy invite link">
              {copied ? <Check className="h-4 w-4" /> : <Copy className="h-4 w-4" />}
            </Button>
          </div>
        ) : (
          <div className="space-y-4">
            <div className="space-y-2">
              <Label>Role</Label>
              <DropdownMenu>
                <DropdownMenuTrigger className={buttonVariants({ variant: "outline", className: "w-full justify-start" })}>
                  {ROLE_LABELS[role]}
                </DropdownMenuTrigger>
                <DropdownMenuContent align="start" className="w-(--anchor-width)">
                  {ASSIGNABLE_ROLES.filter((option) => canAssignRole(actorRole, option)).map((option) => (
                    <DropdownMenuItem key={option} onClick={() => setRole(option)}>
                      {ROLE_LABELS[option]}
                    </DropdownMenuItem>
                  ))}
                </DropdownMenuContent>
              </DropdownMenu>
            </div>
            <div className="space-y-2">
              <Label htmlFor="emailHint">Email (optional)</Label>
              <Input
                id="emailHint"
                type="email"
                placeholder="Restrict the invite to one address"
                value={emailHint}
                onChange={(event) => setEmailHint(event.target.value)}
              />
            </div>
            <div className="space-y-2">
              <Label>Expires in</Label>
              <DropdownMenu>
                <DropdownMenuTrigger className={buttonVariants({ variant: "outline", className: "w-full justify-start" })}>
                  {EXPIRY_OPTIONS.find((option) => option.hours === expiresInHours)?.label}
                </DropdownMenuTrigger>
                <DropdownMenuContent align="start" className="w-(--anchor-width)">
                  {EXPIRY_OPTIONS.map((option) => (
                    <DropdownMenuItem key={option.hours} onClick={() => setExpiresInHours(option.hours)}>
                      {option.label}
                    </DropdownMenuItem>
                  ))}
                </DropdownMenuContent>
              </DropdownMenu>
            </div>
          </div>
        )}

          <DialogFooter>
            {inviteUrl ? (
              <Button onClick={() => setIsOpen(false)}>Done</Button>
            ) : (
              <>
                <Button variant="outline" onClick={() => setIsOpen(false)} disabled={isSubmitting}>
                  Cancel
                </Button>
                <Button onClick={handleCreate} disabled={isSubmitting}>
                  {isSubmitting && <Loader2 className="h-4 w-4 animate-spin" />}
                  Generate link
                </Button>
              </>
            )}
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </>
  );
}
