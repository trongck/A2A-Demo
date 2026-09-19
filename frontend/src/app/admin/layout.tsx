"use client";

import React, { useEffect, useState, createContext, useContext } from "react";
import { useRouter, usePathname } from "next/navigation";
import Link from "next/link";
import { getApiBase } from "./config";

interface AdminUser {
  username: string;
  display_name: string;
  role: string;
}

interface AdminAuthCtx {
  user: AdminUser | null;
  token: string | null;
  logout: () => void;
}

export const AdminAuthContext = createContext<AdminAuthCtx>({
  user: null,
  token: null,
  logout: () => {},
});

export function useAdminAuth() {
  return useContext(AdminAuthContext);
}

// Danh sách điều hướng trang quản trị
const NAV_ITEMS = [
  { label: "Tổng quan", href: "/admin/dashboard" },
  { label: "Mật độ", href: "/admin/crowd" },
  { label: "Bản đồ", href: "/admin/map" },
];

export default function AdminLayout({ children }: { children: React.ReactNode }) {
  const router = useRouter();
  const pathname = usePathname();

  // Khởi tạo trạng thái đồng nhất giữa SSR và Client để tránh lỗi Hydration Mismatch
  const [token, setToken] = useState<string | null>(null);
  const [user, setUser] = useState<AdminUser | null>(null);
  const [loading, setLoading] = useState<boolean>(true);
  const [mounted, setMounted] = useState<boolean>(false);
  const [sidebarOpen, setSidebarOpen] = useState(true);
  const [showLogoutModal, setShowLogoutModal] = useState(false);

  useEffect(() => {
    setMounted(true);
    if (pathname === "/admin/login") {
      setLoading(false);
      return;
    }
    const stored = typeof window !== "undefined" ? localStorage.getItem("admin_token") : null;
    const storedUser = typeof window !== "undefined" ? localStorage.getItem("admin_user") : null;
    if (!stored) {
      router.replace("/admin/login");
      return;
    }
    setToken(stored);
    if (storedUser) {
      try {
        setUser(JSON.parse(storedUser));
      } catch {}
    }
    setLoading(false);

    const apiBase = getApiBase();
    fetch(`${apiBase}/admin/auth/me`, {
      headers: { Authorization: `Bearer ${stored}` },
    })
      .then((r) => {
        if (r.status === 401) {
          localStorage.removeItem("admin_token");
          localStorage.removeItem("admin_user");
          router.replace("/admin/login");
          return null;
        }
        if (r.ok) return r.json();
        return null;
      })
      .then((data) => {
        if (data) {
          setUser(data);
          localStorage.setItem("admin_user", JSON.stringify(data));
        }
      })
      .catch((err) => {
        console.warn("Backend auth verification notice:", err);
      });
  }, [pathname, router]);

  const logout = () => {
    localStorage.removeItem("admin_token");
    localStorage.removeItem("admin_user");
    setToken(null);
    setUser(null);
    router.replace("/admin/login");
  };

  if (pathname === "/admin/login") {
    return <AdminAuthContext.Provider value={{ user, token, logout }}>{children}</AdminAuthContext.Provider>;
  }

  // Cả Server và Client ban đầu đều render màn hình chờ này, loại bỏ 100% Hydration Error
  if (!mounted || loading) {
    return (
      <div className="flex items-center justify-center min-h-screen bg-[#f8fafc]">
        <div className="text-center">
          <div className="w-10 h-10 border-3 border-blue-600 border-t-transparent rounded-full animate-spin mx-auto mb-3" />
          <p className="text-slate-600 text-sm font-medium">Đang kiểm tra xác thực...</p>
        </div>
      </div>
    );
  }

  return (
    <AdminAuthContext.Provider value={{ user, token, logout }}>
      <div className="flex h-screen max-h-screen overflow-hidden bg-[#f1f5f9] text-slate-800 font-sans">
        {/* Sidebar phong cách sáng */}
        <aside
          className={`flex flex-col bg-white border-r border-slate-200 transition-all duration-300 shadow-xs shrink-0 ${
            sidebarOpen ? "w-60" : "w-18"
          }`}
        >
          {/* Logo */}
          <div className="flex items-center gap-3 px-5 py-4 border-b border-slate-100">
            <img src="/logo.png" alt="VinWonders" className="h-8 w-auto object-contain shrink-0" />
            {sidebarOpen && (
              <span className="font-extrabold text-slate-900 text-sm tracking-tight truncate">
                V-AI Điều Phối
              </span>
            )}
          </div>

          {/* Navigation */}
          <nav className="flex-1 py-4 space-y-1 px-3">
            {NAV_ITEMS.map((item) => {
              const active = pathname.startsWith(item.href);
              return (
                <Link
                  key={item.href}
                  href={item.href}
                  className={`flex items-center px-4 py-2.5 rounded-xl text-sm transition-all ${
                    active
                      ? "bg-blue-600 text-white font-bold shadow-sm shadow-blue-500/20"
                      : "text-slate-600 hover:bg-slate-100 hover:text-slate-900 font-medium"
                  }`}
                >
                  <span className="truncate">{item.label}</span>
                </Link>
              );
            })}
          </nav>

          {/* Toggle Sidebar */}
          <button
            onClick={() => setSidebarOpen((v) => !v)}
            className="p-3 text-slate-400 hover:text-slate-700 hover:bg-slate-50 border-t border-slate-100 transition-colors text-xs font-medium text-center cursor-pointer"
          >
            {sidebarOpen ? "Thu gọn menu" : "Mở rộng"}
          </button>
        </aside>

        {/* Main Content */}
        <main className="flex-1 flex flex-col min-w-0 h-full overflow-hidden">
          {/* Topbar */}
          <header className="flex items-center justify-between px-8 py-3.5 bg-white border-b border-slate-200 shadow-2xs shrink-0">
            <div>
              <h1 className="text-base font-extrabold text-slate-900">
                {NAV_ITEMS.find((n) => pathname.startsWith(n.href))?.label ?? "Quản trị"}
              </h1>
              <p className="text-xs text-slate-500 font-medium">
                VinWonders Nha Trang — Hệ thống điều phối V-AI
              </p>
            </div>
            <div className="flex items-center gap-3">
              {/* Icon người đại diện tài khoản */}
              <div
                title={user ? `${user.display_name} (${user.username})` : "Tài khoản điều phối"}
                className="w-9 h-9 rounded-full bg-blue-600 text-white flex items-center justify-center shadow-xs cursor-default"
              >
                <svg
                  xmlns="http://www.w3.org/2000/svg"
                  className="w-4.5 h-4.5"
                  viewBox="0 0 24 24"
                  fill="none"
                  stroke="currentColor"
                  strokeWidth="2"
                  strokeLinecap="round"
                  strokeLinejoin="round"
                >
                  <path d="M19 21v-2a4 4 0 0 0-4-4H9a4 4 0 0 0-4 4v2" />
                  <circle cx="12" cy="7" r="4" />
                </svg>
              </div>

              {/* Nút mở modal xác nhận đăng xuất */}
              <button
                onClick={() => setShowLogoutModal(true)}
                title="Đăng xuất"
                aria-label="Đăng xuất"
                className="w-9 h-9 rounded-full border border-rose-200 bg-rose-50 hover:bg-rose-100 text-rose-600 hover:text-rose-700 transition-all cursor-pointer shadow-2xs flex items-center justify-center group"
              >
                <svg
                  xmlns="http://www.w3.org/2000/svg"
                  className="w-4.5 h-4.5 transition-transform group-hover:translate-x-0.5"
                  viewBox="0 0 24 24"
                  fill="none"
                  stroke="currentColor"
                  strokeWidth="2"
                  strokeLinecap="round"
                  strokeLinejoin="round"
                >
                  <path d="M9 21H5a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h4" />
                  <polyline points="16 17 21 12 16 7" />
                  <line x1="21" y1="12" x2="9" y2="12" />
                </svg>
              </button>
            </div>
          </header>

          {/* Vùng nội dung cố định 1 màn hình */}
          <div className="flex-1 h-full overflow-hidden p-6">{children}</div>
        </main>

        {/* Modal Xác nhận Đăng xuất */}
        {showLogoutModal && (
          <div className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-slate-950/50 backdrop-blur-xs animate-in fade-in duration-150">
            <div className="w-full max-w-sm bg-white rounded-2xl p-6 shadow-2xl border border-slate-200 animate-in zoom-in-95 duration-150">
              <h3 className="text-base font-extrabold text-slate-900">Xác nhận đăng xuất</h3>
              <p className="text-xs text-slate-600 mt-2 leading-relaxed">
                Bạn có chắc chắn muốn đăng xuất khỏi phiên làm việc quản trị V-AI không?
              </p>
              <div className="flex items-center justify-end gap-2.5 mt-6">
                <button
                  type="button"
                  onClick={() => setShowLogoutModal(false)}
                  className="px-4 py-2 rounded-xl border border-slate-200 hover:bg-slate-50 text-slate-700 text-xs font-semibold transition cursor-pointer"
                >
                  Hủy
                </button>
                <button
                  type="button"
                  onClick={() => {
                    setShowLogoutModal(false);
                    logout();
                  }}
                  className="px-4 py-2 rounded-xl bg-rose-600 hover:bg-rose-700 text-white text-xs font-bold transition shadow-xs cursor-pointer"
                >
                  Đăng xuất
                </button>
              </div>
            </div>
          </div>
        )}
      </div>
    </AdminAuthContext.Provider>
  );
}
