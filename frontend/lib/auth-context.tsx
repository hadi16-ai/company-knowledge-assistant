"use client";

import { createContext, useCallback, useContext, useEffect, useState, type ReactNode } from "react";
import { useRouter } from "next/navigation";
import { authApi, clearTokens, getAccessToken, storeTokens, type AuthUser, type RegisterParams } from "@/lib/api";

interface AuthContextValue {
  user: AuthUser | null;
  isLoading: boolean;
  login: (email: string, password: string) => Promise<void>;
  register: (params: RegisterParams) => Promise<void>;
  createWorkspace: (organizationName: string) => Promise<void>;
  logout: () => void;
}

const AuthContext = createContext<AuthContextValue | undefined>(undefined);

export function AuthProvider({ children }: { children: ReactNode }) {
  const [user, setUser] = useState<AuthUser | null>(null);
  const [isLoading, setIsLoading] = useState(true);
  const router = useRouter();

  const loadCurrentUser = useCallback(async () => {
    if (!getAccessToken()) {
      setUser(null);
      setIsLoading(false);
      return;
    }
    try {
      const currentUser = await authApi.me();
      setUser(currentUser);
    } catch {
      clearTokens();
      setUser(null);
    } finally {
      setIsLoading(false);
    }
  }, []);

  useEffect(() => {
    // Deferred via microtask so no setState call happens synchronously within the effect body.
    void Promise.resolve().then(loadCurrentUser);
  }, [loadCurrentUser]);

  const login = useCallback(
    async (email: string, password: string) => {
      const tokens = await authApi.login(email, password);
      storeTokens(tokens);
      await loadCurrentUser();
      router.push("/chat");
    },
    [loadCurrentUser, router]
  );

  const register = useCallback(
    async (params: RegisterParams) => {
      const tokens = await authApi.register(params);
      storeTokens(tokens);
      await loadCurrentUser();
      router.push("/chat");
    },
    [loadCurrentUser, router]
  );

  const createWorkspace = useCallback(
    async (organizationName: string) => {
      const tokens = await authApi.createWorkspace(organizationName);
      storeTokens(tokens);
      await loadCurrentUser();
      router.push("/chat");
    },
    [loadCurrentUser, router]
  );

  const logout = useCallback(() => {
    clearTokens();
    setUser(null);
    router.push("/login");
  }, [router]);

  return (
    <AuthContext.Provider value={{ user, isLoading, login, register, createWorkspace, logout }}>
      {children}
    </AuthContext.Provider>
  );
}

export function useAuth(): AuthContextValue {
  const context = useContext(AuthContext);
  if (!context) throw new Error("useAuth must be used within an AuthProvider");
  return context;
}
