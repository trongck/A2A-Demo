/**
 * frontend/src/app/admin/config.ts
 * Shared configuration and helpers for V-AI Admin Portal
 */

export function getApiBase(): string {
  if (typeof window !== "undefined") {
    const host = window.location.hostname || "127.0.0.1";
    return `http://${host}:8000`;
  }
  return "http://127.0.0.1:8000";
}

export function getStoredToken(): string | null {
  if (typeof window !== "undefined") {
    return localStorage.getItem("admin_token");
  }
  return null;
}

export function getStoredUser(): any | null {
  if (typeof window !== "undefined") {
    const raw = localStorage.getItem("admin_user");
    if (raw) {
      try {
        return JSON.parse(raw);
      } catch {}
    }
  }
  return null;
}

export function clearAdminAuth(): void {
  if (typeof window !== "undefined") {
    localStorage.removeItem("admin_token");
    localStorage.removeItem("admin_user");
  }
}
