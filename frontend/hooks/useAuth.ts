import { useCallback, useEffect, useState } from "react";
import { apiRequest, getToken, isAuthenticated, setToken } from "@/lib/api";
import type { SellerDashboard, User } from "@/types";

interface AuthState {
  user: User | null;
  loading: boolean;
}

/**
 * useAuth hook: registers, logs in, and restores session state.
 * Token persistence uses localStorage; SSR safe.
 */
export function useAuth() {
  const [state, setState] = useState<AuthState>({ user: null, loading: true });

  useEffect(() => {
    async function hydrate() {
      if (!isAuthenticated()) {
        setState({ user: null, loading: false });
        return;
      }
      try {
        const user = await apiRequest<User>("/api/v1/me/", { auth: true });
        setState({ user, loading: false });
      } catch {
        setToken(null);
        setState({ user: null, loading: false });
      }
    }
    hydrate();
  }, []);

  const login = useCallback(
    async (email: string, password: string) => {
      const data = await apiRequest<{ token: string; user: User }>(
        "/api/v1/auth/login/",
        { method: "POST", body: { email, password } }
      );
      setToken(data.token);
      setState({ user: data.user, loading: false });
      return data;
    },
    []
  );

  const register = useCallback(
    async (email: string, username: string, password: string) => {
      const data = await apiRequest<{ token: string; user: User }>(
        "/api/v1/auth/register/",
        { method: "POST", body: { email, username, password } }
      );
      setToken(data.token);
      setState({ user: data.user, loading: false });
      return data;
    },
    []
  );

  const logout = useCallback(async () => {
    try {
      await apiRequest<void>("/api/v1/auth/logout/", { method: "POST", auth: true });
    } catch {
      // Token is cleared regardless; server errors on logout are not blocking.
    }
    setToken(null);
    setState({ user: null, loading: false });
  }, []);

  const loadDashboard = useCallback(async () => {
    return apiRequest<SellerDashboard>("/api/v1/me/dashboard/", { auth: true });
  }, []);

  return { ...state, login, register, logout, loadDashboard };
}