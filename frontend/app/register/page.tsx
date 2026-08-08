"use client";

import { Suspense, useState, type FormEvent } from "react";
import Link from "next/link";
import { useSearchParams } from "next/navigation";
import { toast } from "sonner";
import { AuthShell } from "@/components/layout/auth-shell";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { PasswordInput } from "@/components/ui/password-input";
import { Label } from "@/components/ui/label";
import { Card, CardContent } from "@/components/ui/card";
import { Skeleton } from "@/components/ui/skeleton";
import { Tabs, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { ApiError } from "@/lib/api";
import { useAuth } from "@/lib/auth-context";
import { Loader2 } from "lucide-react";

type RegisterMode = "create" | "invite";

function RegisterForm() {
  const { register } = useAuth();
  const searchParams = useSearchParams();
  const inviteFromUrl = searchParams.get("invite") ?? "";

  const [mode, setMode] = useState<RegisterMode>(inviteFromUrl ? "invite" : "create");
  const [fullName, setFullName] = useState("");
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [confirmPassword, setConfirmPassword] = useState("");
  const [organizationName, setOrganizationName] = useState("");
  const [inviteToken, setInviteToken] = useState(inviteFromUrl);
  const [isSubmitting, setIsSubmitting] = useState(false);

  const passwordsMismatch = confirmPassword.length > 0 && password !== confirmPassword;

  async function handleSubmit(event: FormEvent) {
    event.preventDefault();
    if (password !== confirmPassword) {
      toast.error("Passwords do not match.");
      return;
    }
    setIsSubmitting(true);
    try {
      await register({
        email,
        password,
        fullName,
        organizationName: mode === "create" ? organizationName : undefined,
        inviteToken: mode === "invite" ? inviteToken : undefined,
      });
    } catch (error) {
      toast.error(error instanceof ApiError ? error.message : "Unable to create your account.");
    } finally {
      setIsSubmitting(false);
    }
  }

  return (
    <>
      <Card>
        <CardContent className="space-y-4 pt-6">
          <Tabs value={mode} onValueChange={(value) => setMode(value as RegisterMode)}>
            <TabsList className="w-full">
              <TabsTrigger value="create" className="flex-1">
                Create workspace
              </TabsTrigger>
              <TabsTrigger value="invite" className="flex-1">
                Join with invite
              </TabsTrigger>
            </TabsList>
          </Tabs>
          <form onSubmit={handleSubmit} className="space-y-4">
            <div className="space-y-2">
              <Label htmlFor="fullName">Full name</Label>
              <Input
                id="fullName"
                autoComplete="name"
                required
                value={fullName}
                onChange={(event) => setFullName(event.target.value)}
              />
            </div>
            <div className="space-y-2">
              <Label htmlFor="email">Email</Label>
              <Input
                id="email"
                type="email"
                autoComplete="email"
                required
                value={email}
                onChange={(event) => setEmail(event.target.value)}
              />
            </div>
            {mode === "create" ? (
              <div className="space-y-2">
                <Label htmlFor="organizationName">Workspace name</Label>
                <Input
                  id="organizationName"
                  placeholder="Acme Inc."
                  required
                  value={organizationName}
                  onChange={(event) => setOrganizationName(event.target.value)}
                />
                <p className="text-xs text-muted-foreground">
                  You&apos;ll be the admin of this new workspace.
                </p>
              </div>
            ) : (
              <div className="space-y-2">
                <Label htmlFor="inviteToken">Invite code</Label>
                <Input
                  id="inviteToken"
                  placeholder="Paste your invite code"
                  required
                  value={inviteToken}
                  onChange={(event) => setInviteToken(event.target.value)}
                />
                <p className="text-xs text-muted-foreground">Ask your workspace admin for an invite link.</p>
              </div>
            )}
            <div className="space-y-2">
              <Label htmlFor="password">Password</Label>
              <PasswordInput
                id="password"
                autoComplete="new-password"
                required
                minLength={8}
                value={password}
                onChange={(event) => setPassword(event.target.value)}
              />
              <p className="text-xs text-muted-foreground">At least 8 characters.</p>
            </div>
            <div className="space-y-2">
              <Label htmlFor="confirmPassword">Confirm password</Label>
              <PasswordInput
                id="confirmPassword"
                autoComplete="new-password"
                required
                minLength={8}
                value={confirmPassword}
                onChange={(event) => setConfirmPassword(event.target.value)}
                aria-invalid={passwordsMismatch}
              />
              {passwordsMismatch && <p className="text-xs text-destructive">Passwords do not match.</p>}
            </div>
            <Button type="submit" className="w-full" disabled={isSubmitting || passwordsMismatch}>
              {isSubmitting && <Loader2 className="h-4 w-4 animate-spin" />}
              Create account
            </Button>
          </form>
        </CardContent>
      </Card>
      <p className="text-center text-sm text-muted-foreground">
        Already have an account?{" "}
        <Link href="/login" className="font-medium text-foreground underline underline-offset-4">
          Sign in
        </Link>
      </p>
    </>
  );
}

export default function RegisterPage() {
  return (
    <AuthShell title="Create your workspace account" description="Get started with the Company Knowledge Assistant">
      <Suspense fallback={<Skeleton className="h-[28rem] w-full" />}>
        <RegisterForm />
      </Suspense>
    </AuthShell>
  );
}
