"use client";
import React, { useState, useEffect } from "react";
import Image from "next/image";
import { useRouter } from "next/navigation";
import { getApiBase } from "../config";

export default function AdminLoginPage() {
  const router = useRouter();
  const [username, setUsername] = useState("");
  const [password, setPassword] = useState("");
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");
  const [showPw, setShowPw] = useState(false);

  // Nếu đã có token phiên đăng nhập, tự động chuyển vào Dashboard
  useEffect(() => {
    if (typeof window !== "undefined") {
      const token = localStorage.getItem("admin_token");
      if (token) {
        router.replace("/admin/dashboard");
      }
    }
  }, [router]);

  async function handleLogin(e: React.FormEvent<HTMLFormElement>) {
    e.preventDefault();
    const form = e.currentTarget;
    const u = ((form.elements.namedItem("username") as HTMLInputElement)?.value || username).trim();
    const p = (form.elements.namedItem("password") as HTMLInputElement)?.value || password;

    if (!u || !p) {
      setError("Vui lòng nhập đầy đủ tên đăng nhập và mật khẩu.");
      return;
    }

    setLoading(true);
    setError("");

    try {
      const apiBase = getApiBase();
      const res = await fetch(`${apiBase}/admin/auth/login`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ username: u, password: p }),
      });

      const data = await res.json();
      if (!res.ok) {
        setError(data.detail ?? "Đăng nhập thất bại. Vui lòng kiểm tra lại tài khoản và mật khẩu.");
        return;
      }

      localStorage.setItem("admin_token", data.access_token);
      localStorage.setItem("admin_user", JSON.stringify(data.user));
      // Điều hướng trực tiếp để tải mới trạng thái phiên
      router.replace("/admin/dashboard");
    } catch (err: unknown) {
      console.error("Lỗi yêu cầu đăng nhập:", err);
      setError("Không thể kết nối đến máy chủ Backend (Cổng 8000). Vui lòng thử lại sau.");
    } finally {
      setLoading(false);
    }
  }

  return (
    <div
      className="min-h-screen relative flex items-center justify-center p-4 bg-cover bg-center bg-no-repeat"
      style={{
        backgroundImage: "url('/background_admin.png')",
      }}
    >
      {/* Lớp phủ làm dịu màu nền nhẹ nhàng, giữ trọn cảnh sắc nhưng êm mắt hơn */}
      <div className="absolute inset-0 bg-gradient-to-b from-slate-900/15 via-slate-900/20 to-slate-900/30 backdrop-brightness-95" />

      <div className="relative w-full max-w-md z-10">
        {/* Khung đăng nhập phong cách sáng, gom toàn bộ thông tin vào trong card */}
        <div className="bg-white/95 backdrop-blur-xl border border-white shadow-[0_25px_60px_rgba(0,0,0,0.25)] rounded-3xl p-8 sm:p-10">
          {/* Logo & Tiêu đề được gom trọn vẹn vào bên trong Form */}
          <div className="text-center mb-7">
            <div className="flex justify-center mb-3">
              <Image
                src="/logo.png"
                alt="VinWonders Logo"
                width={260}
                height={64}
                className="h-16 w-auto object-contain"
              />
            </div>
            <h1 className="text-xl font-extrabold text-slate-900 tracking-wide mb-1">
              CỔNG QUẢN TRỊ ĐIỀU PHỐI VIÊN
            </h1>
            <p className="text-slate-600 text-xs font-medium">
              VinWonders Nha Trang — Hệ thống điều phối V-AI
            </p>
          </div>

          <form onSubmit={handleLogin} className="space-y-5">
            <div>
              <label className="block text-xs font-bold text-slate-700 mb-2 uppercase tracking-wider">
                Tên đăng nhập
              </label>
              <input
                id="admin-username"
                name="username"
                type="text"
                autoComplete="username"
                value={username}
                onChange={e => setUsername(e.target.value)}
                placeholder="Nhập tên đăng nhập"
                className="w-full px-4 py-3 bg-white border border-slate-300 rounded-xl text-slate-900 text-sm placeholder-slate-400 outline-none focus:border-blue-600 focus:ring-2 focus:ring-blue-100 transition-all font-medium shadow-sm"
              />
            </div>

            <div>
              <label className="block text-xs font-bold text-slate-700 mb-2 uppercase tracking-wider">
                Mật khẩu
              </label>
              <div className="relative">
                <input
                  id="admin-password"
                  name="password"
                  type={showPw ? "text" : "password"}
                  autoComplete="current-password"
                  value={password}
                  onChange={e => setPassword(e.target.value)}
                  placeholder="Nhập mật khẩu"
                  className="w-full px-4 py-3 bg-white border border-slate-300 rounded-xl text-slate-900 text-sm placeholder-slate-400 outline-none focus:border-blue-600 focus:ring-2 focus:ring-blue-100 transition-all pr-14 font-medium shadow-sm"
                />
                <button
                  type="button"
                  onClick={() => setShowPw(v => !v)}
                  className="absolute right-3 top-1/2 -translate-y-1/2 text-slate-500 hover:text-slate-800 text-xs font-bold px-2 py-1 rounded bg-slate-100 hover:bg-slate-200 transition-colors"
                >
                  {showPw ? "Ẩn" : "Hiện"}
                </button>
              </div>
            </div>

            {/* Thông báo lỗi (không dùng icon) */}
            {error && (
              <div className="px-4 py-3 bg-red-50 border border-red-200 rounded-xl text-red-700 text-xs font-semibold leading-relaxed animate-fade-in">
                {error}
              </div>
            )}

            {/* Nút bấm đăng nhập (không dùng icon) */}
            <button
              id="admin-login-btn"
              type="submit"
              disabled={loading}
              className="w-full py-3.5 bg-blue-600 hover:bg-blue-700 active:bg-blue-800 disabled:opacity-50 disabled:cursor-not-allowed text-white font-bold rounded-xl transition-all duration-150 shadow-md shadow-blue-500/25 flex items-center justify-center cursor-pointer text-sm tracking-wide"
            >
              {loading ? "Đang xác thực..." : "Đăng nhập hệ thống"}
            </button>
          </form>
        </div>
      </div>
    </div>
  );
}
