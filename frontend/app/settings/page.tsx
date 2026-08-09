"use client";

import { useState } from "react";
import { Clock, Loader2, LogOut, Mail, Shield, User as UserIcon } from "lucide-react";
import { toast } from "sonner";
import { AppShell } from "@/components/layout/app-shell";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardFooter, CardHeader, CardTitle } from "@/components/ui/card";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Separator } from "@/components/ui/separator";
import { ThemeToggle } from "@/components/theme-toggle";
import { ApiError } from "@/lib/api";
import { useAuth } from "@/lib/auth-context";
import { ROLE_LABELS } from "@/lib/roles";

function InfoRow({ icon: Icon, label, value }: { icon: typeof UserIcon; label: string; value: string }) {
  return (
    <div className="flex items-center gap-3 py-2.5">
      <div className="flex h-8 w-8 shrink-0 items-center justify-center rounded-lg bg-muted text-muted-foreground">
        <Icon className="h-4 w-4" />
      </div>
      <div className="flex min-w-0 flex-col">
        <span className="text-xs text-muted-foreground">{label}</span>
        <span className="truncate text-sm font-medium">{value}</span>
      </div>
    </div>
  );
}

export default function SettingsPage() {
  const { user, logout, createWorkspace } = useAuth();
  const [isWorkspaceDialogOpen, setIsWorkspaceDialogOpen] = useState(false);
  const [workspaceName, setWorkspaceName] = useState("");
  const [isCreatingWorkspace, setIsCreatingWorkspace] = useState(false);

  async function handleCreateWorkspace() {
    const name = workspaceName.trim();
    if (!name) return;
    setIsCreatingWorkspace(true);
    try {
      await createWorkspace(name);
    } catch (error) {
      toast.error(error instanceof ApiError ? error.message : "Failed to create workspace.");
      setIsCreatingWorkspace(false);
    }
  }

  return (
    <AppShell>
      {user && (
        <div className="flex flex-1 flex-col overflow-y-auto">
          <header className="border-b px-6 py-4">
            <h1 className="text-lg font-semibold">Settings</h1>
            <p className="text-sm text-muted-foreground">Your account, organization, and preferences.</p>
          </header>

          <div className="mx-auto flex w-full max-w-2xl flex-col gap-6 px-6 py-6">
            <Card>
              <CardHeader>
                <CardTitle>Account</CardTitle>
                <CardDescription>Your profile within this organization.</CardDescription>
              </CardHeader>
              <CardContent className="divide-y">
                <InfoRow icon={UserIcon} label="Full name" value={user.full_name} />
                <InfoRow icon={Mail} label="Email" value={user.email} />
                <div className="flex items-center gap-3 py-2.5">
                  <div className="flex h-8 w-8 shrink-0 items-center justify-center rounded-lg bg-muted text-muted-foreground">
                    <Shield className="h-4 w-4" />
                  </div>
                  <div className="flex min-w-0 flex-col">
                    <span className="text-xs text-muted-foreground">Role</span>
                    <Badge variant="secondary" className="mt-0.5 w-fit">
                      {ROLE_LABELS[user.role]}
                    </Badge>
                  </div>
                </div>
                {user.expires_at && (
                  <InfoRow
                    icon={Clock}
                    label="Access expires"
                    value={new Date(user.expires_at).toLocaleString()}
                  />
                )}
              </CardContent>
            </Card>

            <Card>
              <CardHeader>
                <CardTitle>Organization</CardTitle>
                <CardDescription>The workspace your account belongs to.</CardDescription>
              </CardHeader>
              <CardContent>
                <InfoRow icon={UserIcon} label="Organization" value={user.org_name} />
              </CardContent>
              <CardFooter>
                <Button variant="outline" size="sm" onClick={() => setIsWorkspaceDialogOpen(true)}>
                  Create your own workspace
                </Button>
              </CardFooter>
            </Card>

            <Card>
              <CardHeader>
                <CardTitle>Appearance</CardTitle>
                <CardDescription>Choose how the app looks on this device.</CardDescription>
              </CardHeader>
              <CardContent>
                <ThemeToggle />
              </CardContent>
            </Card>

            <Card>
              <CardHeader>
                <CardTitle>More settings</CardTitle>
                <CardDescription>
                  Notification preferences and connected integrations are coming soon.
                </CardDescription>
              </CardHeader>
            </Card>

            <Separator />

            <Button variant="outline" className="w-fit" onClick={logout}>
              <LogOut className="h-4 w-4" />
              Sign out
            </Button>
          </div>
        </div>
      )}

      <Dialog
        open={isWorkspaceDialogOpen}
        onOpenChange={(open) => {
          if (isCreatingWorkspace) return;
          setIsWorkspaceDialogOpen(open);
          if (!open) setWorkspaceName("");
        }}
      >
        <DialogContent>
          <DialogHeader>
            <DialogTitle>Create your own workspace</DialogTitle>
            <DialogDescription>
              This moves your account out of &quot;{user?.org_name}&quot; into a brand-new workspace where
              you&apos;re the Company Admin. Your current workspace and its other members are unaffected —
              you just won&apos;t have access to their documents or conversations anymore.
            </DialogDescription>
          </DialogHeader>
          <div className="space-y-2">
            <Label htmlFor="workspaceName">Workspace name</Label>
            <Input
              id="workspaceName"
              value={workspaceName}
              onChange={(event) => setWorkspaceName(event.target.value)}
              placeholder="Acme Inc."
              disabled={isCreatingWorkspace}
            />
          </div>
          <DialogFooter>
            <Button
              variant="outline"
              onClick={() => setIsWorkspaceDialogOpen(false)}
              disabled={isCreatingWorkspace}
            >
              Cancel
            </Button>
            <Button onClick={handleCreateWorkspace} disabled={isCreatingWorkspace || !workspaceName.trim()}>
              {isCreatingWorkspace && <Loader2 className="h-4 w-4 animate-spin" />}
              Create workspace
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </AppShell>
  );
}
