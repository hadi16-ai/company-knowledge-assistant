"use client";

import * as React from "react";
import { useTheme } from "next-themes";
import { Monitor, Moon, Sun } from "lucide-react";

import { Button } from "@/components/ui/button";

const OPTIONS = [
  { value: "light", label: "Light", icon: Sun },
  { value: "dark", label: "Dark", icon: Moon },
  { value: "system", label: "System", icon: Monitor },
] as const;

export function ThemeToggle() {
  const { theme, setTheme } = useTheme();
  // next-themes only knows the real theme after mount (it reads localStorage /
  // matchMedia client-side); guard the "active" styling so SSR and the first
  // client render match and React doesn't warn about a hydration mismatch.
  const [mounted, setMounted] = React.useState(false);
  React.useEffect(() => {
    // Deferred via microtask so no setState call happens synchronously within the effect body.
    void Promise.resolve().then(() => setMounted(true));
  }, []);

  return (
    <div className="inline-flex items-center gap-1 rounded-lg border border-border bg-muted/40 p-1">
      {OPTIONS.map(({ value, label, icon: Icon }) => (
        <Button
          key={value}
          type="button"
          variant={mounted && theme === value ? "secondary" : "ghost"}
          size="sm"
          onClick={() => setTheme(value)}
          className="gap-1.5"
        >
          <Icon className="h-3.5 w-3.5" />
          {label}
        </Button>
      ))}
    </div>
  );
}
