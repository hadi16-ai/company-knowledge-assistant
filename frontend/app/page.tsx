"use client";

import { useEffect } from "react";
import { useRouter } from "next/navigation";
import { useAuth } from "@/lib/auth-context";
import { Skeleton } from "@/components/ui/skeleton";

export default function Home() {
  const { user, isLoading } = useAuth();
  const router = useRouter();

  useEffect(() => {
    if (isLoading) return;
    router.replace(user ? "/chat" : "/login");
  }, [isLoading, user, router]);

  return (
    <div className="flex flex-1 items-center justify-center">
      <Skeleton className="h-8 w-48" />
    </div>
  );
}
