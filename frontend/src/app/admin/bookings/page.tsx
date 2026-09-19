"use client";
import React, { useEffect, useState, useCallback } from "react";
import Link from "next/link";
import { useAdminAuth } from "../layout";
import { getApiBase } from "../config";

interface BookingItem {
  session_id: string;
  admin_status: string;
  group_size: number;
  plan_count: number;
  last_message_preview: string;
  created_at: string;
  updated_at: string;
  scenario_id: string;
}

interface BookingsResponse {
  total: number;
  page: number;
  page_size: number;
  items: BookingItem[];
}

const STATUS_OPTS = [
  { value: "all", label: "Tất cả" },
  { value: "pending", label: "Chờ duyệt" },
  { value: "confirmed", label: "Đã xác nhận" },
  { value: "rejected", label: "Từ chối" },
];

const STATUS_STYLE: Record<string, string> = {
  pending: "bg-amber-50 text-amber-700 border-amber-200",
  confirmed: "bg-emerald-50 text-emerald-700 border-emerald-200",
  rejected: "bg-rose-50 text-rose-700 border-rose-200",
};

const STATUS_LABEL: Record<string, string> = {
  pending: "Chờ duyệt",
  confirmed: "Đã xác nhận",
  rejected: "Từ chối",
};

export default function BookingsPage() {
  const { token } = useAdminAuth();
  const [data, setData] = useState<BookingsResponse | null>(null);
  const [statusFilter, setStatusFilter] = useState("all");
  const [page, setPage] = useState(1);
  const [loading, setLoading] = useState(false);

  const fetchBookings = useCallback(async () => {
    const effectiveToken = token || (typeof window !== "undefined" ? localStorage.getItem("admin_token") : null);
    if (!effectiveToken) return;
    setLoading(true);
    try {
      const apiBase = getApiBase();
      const params = new URLSearchParams({ page: String(page), page_size: "20" });
      if (statusFilter !== "all") params.append("admin_status", statusFilter);
      const res = await fetch(`${apiBase}/admin/bookings?${params}`, {
        headers: { Authorization: `Bearer ${effectiveToken}` }
      });
      if (res.ok) setData(await res.json());
    } finally {
      setLoading(false);
    }
  }, [token, statusFilter, page]);

  useEffect(() => { fetchBookings(); }, [fetchBookings]);
  useEffect(() => { setPage(1); }, [statusFilter]);

  const totalPages = data ? Math.ceil(data.total / data.page_size) : 1;

  return (
    <div className="space-y-6">
      <div className="flex flex-wrap items-center justify-between gap-4">
        <div>
          <h2 className="text-2xl font-black text-slate-900 tracking-tight">Quản lý đặt lịch</h2>
          <p className="text-xs text-slate-500 font-medium mt-0.5">
            {data ? `Tổng cộng ${data.total} phiên tư vấn trong hệ thống` : "Đang tải dữ liệu..."}
          </p>
        </div>
        <button
          onClick={fetchBookings}
          disabled={loading}
          className="px-4 py-2 bg-blue-600 hover:bg-blue-700 disabled:opacity-50 text-white text-xs font-bold rounded-xl transition-all shadow-xs cursor-pointer"
        >
          {loading ? "Đang tải..." : "Làm mới"}
        </button>
      </div>

      {/* Bộ lọc trạng thái */}
      <div className="flex gap-1.5 bg-white border border-slate-200/80 rounded-2xl p-1.5 w-fit shadow-2xs">
        {STATUS_OPTS.map(opt => (
          <button
            key={opt.value}
            onClick={() => setStatusFilter(opt.value)}
            className={`px-4 py-2 rounded-xl text-xs font-bold transition-all cursor-pointer ${
              statusFilter === opt.value
                ? "bg-blue-600 text-white shadow-xs"
                : "text-slate-600 hover:text-slate-900 hover:bg-slate-100/80"
            }`}
          >
            {opt.label}
          </button>
        ))}
      </div>

      {/* Bảng dữ liệu phong cách sáng */}
      <div className="bg-white border border-slate-200/80 rounded-2xl overflow-hidden shadow-xs">
        <div className="overflow-x-auto">
          <table className="w-full text-sm text-left">
            <thead className="bg-slate-50/80 border-b border-slate-200 text-xs font-bold text-slate-600 uppercase tracking-wider">
              <tr>
                <th className="px-5 py-3.5">Mã phiên (Session ID)</th>
                <th className="px-5 py-3.5">Số khách</th>
                <th className="px-5 py-3.5">Số lịch trình</th>
                <th className="px-5 py-3.5">Tin nhắn gần nhất</th>
                <th className="px-5 py-3.5">Trạng thái</th>
                <th className="px-5 py-3.5">Thời gian cập nhật</th>
                <th className="px-5 py-3.5 text-right">Thao tác</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-slate-100">
              {loading && !data?.items?.length ? (
                <tr>
                  <td colSpan={7} className="px-5 py-12 text-center text-slate-400 font-medium">
                    Đang tải danh sách đặt lịch...
                  </td>
                </tr>
              ) : data?.items?.length === 0 ? (
                <tr>
                  <td colSpan={7} className="px-5 py-12 text-center text-slate-400 font-medium">
                    Không có phiên đặt lịch nào phù hợp với bộ lọc
                  </td>
                </tr>
              ) : (
                data?.items?.map(b => (
                  <tr key={b.session_id} className="hover:bg-slate-50/80 transition-colors group">
                    <td className="px-5 py-4">
                      <span className="font-mono text-xs font-bold text-slate-800">{b.session_id}</span>
                    </td>
                    <td className="px-5 py-4 text-xs font-semibold text-slate-700">
                      {b.group_size > 0 ? `${b.group_size} người` : "Chưa xác định"}
                    </td>
                    <td className="px-5 py-4 text-xs font-bold text-slate-900">{b.plan_count}</td>
                    <td className="px-5 py-4 max-w-[240px]">
                      <p className="text-xs text-slate-500 font-medium truncate">{b.last_message_preview || "—"}</p>
                    </td>
                    <td className="px-5 py-4">
                      <span className={`inline-flex items-center px-2.5 py-0.5 rounded-full text-xs font-bold border ${STATUS_STYLE[b.admin_status] ?? STATUS_STYLE.pending}`}>
                        {STATUS_LABEL[b.admin_status] ?? b.admin_status}
                      </span>
                    </td>
                    <td className="px-5 py-4 text-xs text-slate-500 font-medium">
                      {new Date(b.updated_at).toLocaleString("vi-VN", { dateStyle: "short", timeStyle: "short" })}
                    </td>
                    <td className="px-5 py-4 text-right">
                      <Link
                        href={`/admin/bookings/${b.session_id}`}
                        className="text-xs font-bold text-blue-600 hover:text-blue-800 transition-colors"
                      >
                        Xem chi tiết
                      </Link>
                    </td>
                  </tr>
                ))
              )}
            </tbody>
          </table>
        </div>

        {/* Phân trang */}
        {totalPages > 1 && (
          <div className="px-5 py-4 border-t border-slate-100 bg-slate-50/50 flex items-center justify-between">
            <span className="text-xs text-slate-500 font-medium">
              Trang {page} trên tổng số {totalPages}
            </span>
            <div className="flex gap-2">
              <button
                onClick={() => setPage(p => Math.max(1, p - 1))}
                disabled={page === 1}
                className="px-3.5 py-1.5 text-xs font-bold bg-white border border-slate-200 hover:bg-slate-50 disabled:opacity-40 text-slate-700 rounded-xl transition-all cursor-pointer"
              >
                Trang trước
              </button>
              <button
                onClick={() => setPage(p => Math.min(totalPages, p + 1))}
                disabled={page === totalPages}
                className="px-3.5 py-1.5 text-xs font-bold bg-white border border-slate-200 hover:bg-slate-50 disabled:opacity-40 text-slate-700 rounded-xl transition-all cursor-pointer"
              >
                Trang sau
              </button>
            </div>
          </div>
        )}
      </div>
    </div>
  );
}
