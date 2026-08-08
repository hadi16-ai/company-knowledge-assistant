"use client";

import { useState } from "react";
import { Clock, Loader2, MoreVertical, ShieldOff, UserCheck } from "lucide-react";
import type { OrgMember, UserRole } from "@/lib/api";
import { ASSIGNABLE_ROLES, ROLE_LABELS, canAssignRole } from "@/lib/roles";
import { Badge } from "@/components/ui/badge";
import { Button, buttonVariants } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuSeparator,
  DropdownMenuSub,
  DropdownMenuSubContent,
  DropdownMenuSubTrigger,
  DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu";

/** Formats a Date as the value a <input type="datetime-local"> expects, in local time. */
function toDatetimeLocalValue(date: Date): string {
  const pad = (n: number) => String(n).padStart(2, "0");
  return `${date.getFullYear()}-${pad(date.getMonth() + 1)}-${pad(date.getDate())}T${pad(date.getHours())}:${pad(date.getMinutes())}`;
}

interface MemberRowProps {
  member: OrgMember;
  actorRole: UserRole;
  isSelf: boolean;
  onChangeRole: (member: OrgMember, role: UserRole) => Promise<void>;
  onToggleActive: (member: OrgMember) => Promise<void>;
  onSetExpiry: (member: OrgMember, expiresAt: string | null) => Promise<void>;
}

export function MemberRow({ member, actorRole, isSelf, onChangeRole, onToggleActive, onSetExpiry }: MemberRowProps) {
  const [isBusy, setIsBusy] = useState(false);
  const [isExpiryOpen, setIsExpiryOpen] = useState(false);
  const [expiryValue, setExpiryValue] = useState(
    member.expires_at ? toDatetimeLocalValue(new Date(member.expires_at)) : ""
  );

  const editable = !isSelf && canAssignRole(actorRole, member.role);

  async function withBusy(action: () => Promise<void>) {
    setIsBusy(true);
    try {
      await action();
    } finally {
      setIsBusy(false);
    }
  }

  async function handleSaveExpiry() {
    await withBusy(async () => {
      await onSetExpiry(member, expiryValue ? new Date(expiryValue).toISOString() : null);
      setIsExpiryOpen(false);
    });
  }

  return (
    <div className="flex items-center justify-between gap-4 border-b px-4 py-3 last:border-b-0">
      <div className="flex min-w-0 items-center gap-3">
        <div className="flex h-8 w-8 shrink-0 items-center justify-center rounded-full bg-secondary text-xs font-semibold">
          {member.full_name.charAt(0).toUpperCase()}
        </div>
        <div className="min-w-0">
          <p className="truncate text-sm font-medium">
            {member.full_name}
            {isSelf && <span className="ml-1.5 text-xs text-muted-foreground">(you)</span>}
          </p>
          <p className="truncate text-xs text-muted-foreground">{member.email}</p>
        </div>
      </div>

      <div className="flex shrink-0 items-center gap-2">
        <Badge variant="secondary">{ROLE_LABELS[member.role]}</Badge>
        {!member.is_active && (
          <Badge variant="destructive" className="gap-1">
            <ShieldOff className="h-3 w-3" />
            Inactive
          </Badge>
        )}
        {member.role === "guest" && member.expires_at && (
          <Badge variant="outline" className="gap-1">
            <Clock className="h-3 w-3" />
            Expires {new Date(member.expires_at).toLocaleDateString()}
          </Badge>
        )}
      </div>

      {editable && (
        <DropdownMenu>
          <DropdownMenuTrigger
            disabled={isBusy}
            aria-label={`Actions for ${member.full_name}`}
            className={buttonVariants({ variant: "ghost", size: "icon", className: "shrink-0 text-muted-foreground" })}
          >
            {isBusy ? <Loader2 className="h-4 w-4 animate-spin" /> : <MoreVertical className="h-4 w-4" />}
          </DropdownMenuTrigger>
          <DropdownMenuContent align="end">
            <DropdownMenuSub>
              <DropdownMenuSubTrigger>Change role</DropdownMenuSubTrigger>
              <DropdownMenuSubContent>
                {ASSIGNABLE_ROLES.filter((role) => role !== member.role && canAssignRole(actorRole, role)).map(
                  (role) => (
                    <DropdownMenuItem key={role} onClick={() => withBusy(() => onChangeRole(member, role))}>
                      {ROLE_LABELS[role]}
                    </DropdownMenuItem>
                  )
                )}
              </DropdownMenuSubContent>
            </DropdownMenuSub>
            {member.role === "guest" && (
              <DropdownMenuItem onClick={() => setIsExpiryOpen(true)}>
                <Clock className="h-4 w-4" />
                Set access expiry
              </DropdownMenuItem>
            )}
            <DropdownMenuSeparator />
            <DropdownMenuItem
              variant={member.is_active ? "destructive" : "default"}
              onClick={() => withBusy(() => onToggleActive(member))}
            >
              {member.is_active ? <ShieldOff className="h-4 w-4" /> : <UserCheck className="h-4 w-4" />}
              {member.is_active ? "Deactivate" : "Reactivate"}
            </DropdownMenuItem>
          </DropdownMenuContent>
        </DropdownMenu>
      )}

      <Dialog open={isExpiryOpen} onOpenChange={setIsExpiryOpen}>
        <DialogContent>
          <DialogHeader>
            <DialogTitle>Set access expiry for {member.full_name}</DialogTitle>
            <DialogDescription>
              This guest account stops working at the chosen time. Leave blank for no time limit.
            </DialogDescription>
          </DialogHeader>
          <Input
            type="datetime-local"
            value={expiryValue}
            onChange={(event) => setExpiryValue(event.target.value)}
          />
          <DialogFooter>
            <Button variant="outline" onClick={() => setIsExpiryOpen(false)} disabled={isBusy}>
              Cancel
            </Button>
            <Button onClick={handleSaveExpiry} disabled={isBusy}>
              {isBusy && <Loader2 className="h-4 w-4 animate-spin" />}
              Save
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </div>
  );
}
