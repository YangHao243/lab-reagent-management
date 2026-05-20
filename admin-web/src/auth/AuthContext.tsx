import { createContext, useContext, useEffect, useMemo, useState } from "react";
import type { ReactNode } from "react";
import { apiClient } from "../api/client";
import {
  clearAuthStorage,
  getStoredToken,
  getStoredUser,
  saveAuthStorage,
  saveCurrentUser,
  type CurrentUser,
  type UserRole,
} from "./storage";

type LoginResponse = {
  access_token: string;
  token_type: string;
  user: CurrentUser;
};

type AuthContextValue = {
  user: CurrentUser | null;
  loading: boolean;
  isAuthenticated: boolean;
  login: (username: string, password: string) => Promise<void>;
  logout: () => void;
  hasRole: (...roles: UserRole[]) => boolean;
};

const AuthContext = createContext<AuthContextValue | null>(null);

export function AuthProvider({ children }: { children: ReactNode }) {
  const [user, setUser] = useState<CurrentUser | null>(() => getStoredUser());
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    const token = getStoredToken();
    if (!token) {
      clearAuthStorage();
      setUser(null);
      setLoading(false);
      return;
    }

    apiClient
      .get<CurrentUser>("/users/me")
      .then((response) => {
        setUser(response.data);
        saveCurrentUser(response.data);
      })
      .catch(() => {
        clearAuthStorage();
        setUser(null);
      })
      .finally(() => setLoading(false));
  }, []);

  const value = useMemo<AuthContextValue>(
    () => ({
      user,
      loading,
      isAuthenticated: Boolean(user && getStoredToken()),
      login: async (username: string, password: string) => {
        const response = await apiClient.post<LoginResponse>("/users/login", {
          username,
          password,
        });
        saveAuthStorage(response.data.access_token, response.data.user);
        setUser(response.data.user);
      },
      logout: () => {
        clearAuthStorage();
        setUser(null);
      },
      hasRole: (...roles: UserRole[]) => {
        return Boolean(user && roles.includes(user.role));
      },
    }),
    [loading, user],
  );

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
}

export function useAuth() {
  const context = useContext(AuthContext);
  if (!context) {
    throw new Error("useAuth must be used within AuthProvider");
  }
  return context;
}
