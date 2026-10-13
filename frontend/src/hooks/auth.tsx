import { useQuery, useQueryClient } from "@tanstack/react-query";
import { createContext, useContext, useEffect, type ReactNode } from "react";

import { api, ApiError, setCsrfToken, setUnauthorizedHandler } from "../api/client";
import type { Me } from "../types/api";

interface AuthValue {
  me: Me | null;
  loading: boolean;
  can: (perm: string) => boolean;
  setMe: (me: Me | null) => void;
}

const AuthContext = createContext<AuthValue | null>(null);

export function AuthProvider({ children }: { children: ReactNode }) {
  const qc = useQueryClient();
  const query = useQuery({
    queryKey: ["me"],
    queryFn: async () => {
      try {
        return await api.get<Me>("/auth/me");
      } catch (e) {
        if (e instanceof ApiError && e.status === 401) return null;
        throw e;
      }
    },
    staleTime: 5 * 60_000,
    retry: 1,
  });
  const me = query.data ?? null;

  useEffect(() => {
    setCsrfToken(me?.csrf_token ?? null);
  }, [me]);

  useEffect(() => {
    // Any 401 from the API (expired session) sends the user back to the login screen.
    setUnauthorizedHandler(() => {
      setCsrfToken(null);
      qc.setQueryData(["me"], null);
      qc.removeQueries({ predicate: (q) => q.queryKey[0] !== "me" });
    });
  }, [qc]);

  const value: AuthValue = {
    me,
    loading: query.isLoading,
    can: (perm) => !!me?.permissions.includes(perm),
    setMe: (next) => {
      setCsrfToken(next?.csrf_token ?? null);
      qc.setQueryData(["me"], next);
      if (!next) qc.removeQueries({ predicate: (q) => q.queryKey[0] !== "me" });
    },
  };
  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
}

export function useAuth(): AuthValue {
  const v = useContext(AuthContext);
  if (!v) throw new Error("useAuth must be used inside AuthProvider");
  return v;
}
