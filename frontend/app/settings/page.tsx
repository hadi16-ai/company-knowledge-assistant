"use client";

import { LogOut, Mail, Shield, User as UserIcon } from "lucide-react";
import { AppShell } from "@/components/layout/app-shell";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Separator } from "@/components/ui/separator";
import { ThemeToggle } from "@/components/theme-toggle";
import { useAuth } from "@/lib/auth-context";

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
  const { user, logout } = useAuth();

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
                    <Badge variant="secondary" className="mt-0.5 w-fit capitalize">
                      {user.role}
                    </Badge>
                  </div>
                </div>
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
    </AppShell>
  );
}
