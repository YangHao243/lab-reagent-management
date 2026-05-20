export const ACCESS_TOKEN_KEY = "access_token";
export const CURRENT_USER_KEY = "current_user";

export type UserRole = "member" | "manager" | "admin" | "superadmin";

export type CurrentUser = {
  id: number;
  username: string;
  full_name?: string | null;
  role: UserRole;
  email?: string | null;
  phone?: string | null;
  is_active: boolean;
  created_at?: string;
  updated_at?: string;
};

export function getStoredToken() {
  return localStorage.getItem(ACCESS_TOKEN_KEY);
}

export function getStoredUser() {
  const rawUser = localStorage.getItem(CURRENT_USER_KEY);
  if (!rawUser) {
    return null;
  }

  try {
    return JSON.parse(rawUser) as CurrentUser;
  } catch {
    localStorage.removeItem(CURRENT_USER_KEY);
    return null;
  }
}

export function saveAuthStorage(token: string, user: CurrentUser) {
  localStorage.setItem(ACCESS_TOKEN_KEY, token);
  localStorage.setItem(CURRENT_USER_KEY, JSON.stringify(user));
}

export function saveCurrentUser(user: CurrentUser) {
  localStorage.setItem(CURRENT_USER_KEY, JSON.stringify(user));
}

export function clearAuthStorage() {
  localStorage.removeItem(ACCESS_TOKEN_KEY);
  localStorage.removeItem(CURRENT_USER_KEY);
}
