"use client";
import React, { useEffect, useState, useCallback } from "react";
import Link from "next/link";
import { useAdminAuth } from "../layout";
import { getApiBase } from "../config";

interface Stats {
  total_sessions: number;
  pending: number;
  confirmed: number;
  rejected: number;
  total_plans: number;
}

interface Attraction {
  service_id: string;
  name: string;
  zone_id: string;
  indoor: boolean;
  operating_status: string;
  current_people: number | null;
  capacity: number;
  occupancy_rate: number | null;
  crowd_level: string;
  wait_minutes: number | null;
}

interface ZoneData {
  zone_id: string;
  zone_name: string;
  attractions: Attraction[];
}

interface BookingItem {
  session_id: string;
  admin_status: string;
  group_size: number;
  plan_count: number;
  last_message_preview: string;
  created_at: string;
  updated_at: string;
}

const CROWD_BADGES: Record<string, { bg: string; text: string; label: string }> = {
  low: { bg: "bg-emerald-50 border-emerald-200", text: "text-emerald-700", label: "Vắng" },
  medium: { bg: "bg-amber-50 border-amber-200", text: "text-amber-700", label: "Bình thường" },
  high: { bg: "bg-rose-50 border-rose-200", text: "text-rose-700", label: "Đông đúc" },
  unknown: { bg: "bg-slate-50 border-slate-200", text: "text-slate-600", label: "Chưa rõ" },
};

const STATUS_BADGES: Record<string, { bg: string; label: string }> = {
  pending: { bg: "bg-amber-50 text-amber-700 border border-amber-200", label: "Chờ duyệt" },
  confirmed: { bg: "bg-emerald-50 text-emerald-700 border border-emerald-200", label: "Đã xác nhận" },
  rejected: { bg: "bg-rose-50 text-rose-700 border border-rose-200", label: "Từ chối" },
};

// StatCard phong cách sáng, bỏ hoàn toàn icon
function StatCard({ label, value, accentColor }: { label: string; value: number; accentColor: string }) {
  return (
    <div className={`bg-white border border-slate-200/80 shadow-xs rounded-2xl p-5 hover:shadow-sm transition-all border-l-4 ${accentColor}`}>
      <p className="text-3xl font-extrabold text-slate-900 tracking-tight">{value}</p>
      <p className="text-xs font-bold text-slate-500 mt-1 uppercase tracking-wider">{label}</p>
    </div>
  );
}

export default function DashboardPage() {
  const { token } = useAdminAuth();
  const [stats, setStats] = useState<Stats | null>(null);
  const [zones, setZones] = useState<ZoneData[]>([]);
  const [recent, setRecent] = useState<BookingItem[]>([]);
  const [lastRefresh, setLastRefresh] = useState<Date | null>(null);

  const fetchData = useCallback(async () => {
    const effectiveToken = token || (typeof window !== "undefined" ? localStorage.getItem("admin_token") : null);
    if (!effectiveToken) return;

    const authHeader: Record<string, string> = { Authorization: `Bearer ${effectiveToken}` };
    const apiBase = getApiBase();

    try {
      const [statsRes, crowdRes, bookingsRes] = await Promise.all([
        fetch(`${apiBase}/admin/bookings/stats`, { headers: authHeader }),
        fetch(`${apiBase}/admin/crowd/overview`, { headers: authHeader }),
        fetch(`${apiBase}/admin/bookings?page=1&page_size=5`, { headers: authHeader }),
      ]);
      if (statsRes.ok) setStats(await statsRes.json());
      if (crowdRes.ok) { const d = await crowdRes.json(); setZones(d.zones ?? []); }
      if (bookingsRes.ok) { const d = await bookingsRes.json(); setRecent(d.items ?? []); }
      setLastRefresh(new Date());
    } catch (err) {
      console.warn("Dashboard fetch error:", err);
    }
  }, [token]);

  useEffect(() => {
    fetchData();
    const id = setInterval(fetchData, 30000);
    return () => clearInterval(id);
  }, [fetchData]);

  const allAttractions = zones.flatMap(z => z.attractions);

  return (
    <div className="space-y-6">
      {/* Tiêu đề & Làm mới */}
      <div className="flex flex-wrap items-center justify-between gap-4">
        <div>
          <h2 className="text-2xl font-black text-slate-900 tracking-tight">Tổng quan hệ thống</h2>
          <p className="text-xs text-slate-500 font-medium mt-0.5">Dữ liệu tự động cập nhật định kỳ mỗi 30 giây</p>
        </div>
        <div className="flex items-center gap-3">
          {lastRefresh && (
            <span className="text-xs text-slate-500 font-medium">
              Cập nhật lúc: {lastRefresh.toLocaleTimeString("vi-VN")}
            </span>
          )}
          <button
            onClick={fetchData}
            className="px-4 py-2 bg-blue-600 hover:bg-blue-700 active:bg-blue-800 text-white text-xs font-bold rounded-xl transition-all shadow-xs cursor-pointer"
          >
            Làm mới dữ liệu
          </button>
        </div>
      </div>

      {/* Lưới thẻ chỉ số - Bỏ toàn bộ icon, thiết kế thanh lịch */}
      {stats && (
        <div className="grid grid-cols-2 lg:grid-cols-4 gap-4">
          <StatCard label="Tổng số phiên" value={stats.total_sessions} accentColor="border-blue-600" />
          <StatCard label="Đang chờ duyệt" value={stats.pending} accentColor="border-amber-500" />
          <StatCard label="Đã xác nhận" value={stats.confirmed} accentColor="border-emerald-600" />
          <StatCard label="Đã từ chối" value={stats.rejected} accentColor="border-rose-500" />
        </div>
      )}

      <div className="grid grid-cols-1 xl:grid-cols-2 gap-6">
        {/* Xem trước mật độ khu vui chơi */}
        <div className="bg-white border border-slate-200/80 rounded-2xl p-6 shadow-xs">
          <div className="flex items-center justify-between mb-5">
            <h3 className="font-extrabold text-slate-900 text-base">Mật độ các điểm vui chơi</h3>
            <Link href="/admin/crowd" className="text-xs font-bold text-blue-600 hover:text-blue-700 transition-colors">
              Xem chi tiết bản đồ
            </Link>
          </div>
          <div className="grid grid-cols-2 sm:grid-cols-3 gap-3">
            {allAttractions.slice(0, 12).map(a => {
              const badge = CROWD_BADGES[a.crowd_level] ?? CROWD_BADGES.unknown;
              return (
                <div
                  key={a.service_id}
                  className="bg-slate-50/80 rounded-xl p-3.5 border border-slate-200/70 hover:border-slate-300 hover:bg-slate-100/70 transition-all"
                >
                  <p className="text-xs text-slate-800 font-bold leading-tight truncate">{a.name}</p>
                  <div className="mt-2 flex items-center justify-between">
                    <span className={`text-[10px] font-bold px-2 py-0.5 rounded border ${badge.bg} ${badge.text}`}>
                      {badge.label}
                    </span>
                    <span className="text-[11px] font-semibold text-slate-600">
                      {a.operating_status === "open" && a.current_people !== null
                        ? `${a.current_people}/${a.capacity} khách`
                        : "Đóng cửa"}
                    </span>
                  </div>
                </div>
              );
            })}
          </div>

          {/* Chú giải trạng thái - Bỏ toàn bộ icon */}
          <div className="flex flex-wrap items-center gap-4 mt-5 pt-4 border-t border-slate-100 text-xs">
            <span className="font-bold text-slate-500">Mức độ:</span>
            <span className="text-emerald-700 font-semibold">Vắng (Dưới 40%)</span>
            <span className="text-amber-700 font-semibold">Bình thường (40 - 70%)</span>
            <span className="text-rose-700 font-semibold">Đông đúc (Trên 70%)</span>
          </div>
        </div>

        {/* Danh sách phiên đặt lịch gần nhất */}
        <div className="bg-white border border-slate-200/80 rounded-2xl p-6 shadow-xs">
          <div className="flex items-center justify-between mb-5">
            <h3 className="font-extrabold text-slate-900 text-base">Phiên đặt lịch gần nhất</h3>
            <Link href="/admin/bookings" className="text-xs font-bold text-blue-600 hover:text-blue-700 transition-colors">
              Xem tất cả phiên
            </Link>
          </div>

          {recent.length === 0 ? (
            <div className="text-center py-12 text-slate-400 text-sm font-medium">
              Chưa có phiên đặt lịch nào trong hệ thống
            </div>
          ) : (
            <div className="space-y-2.5">
              {recent.map(b => {
                const statusInfo = STATUS_BADGES[b.admin_status] ?? STATUS_BADGES.pending;
                return (
                  <Link
                    key={b.session_id}
                    href={`/admin/bookings/${b.session_id}`}
                    className="flex items-center justify-between gap-3 px-4 py-3.5 rounded-xl border border-slate-100 hover:border-slate-300 hover:bg-slate-50/80 transition-all group"
                  >
                    <div className="flex-1 min-w-0">
                      <p className="text-xs font-mono font-bold text-slate-700 truncate">{b.session_id}</p>
                      <p className="text-xs text-slate-500 mt-0.5 truncate font-medium">
                        {b.last_message_preview || "(Chưa có tin nhắn)"}
                      </p>
                    </div>
                    <div className="flex flex-col items-end gap-1 shrink-0">
                      <span className={`text-[11px] px-2.5 py-0.5 rounded-full font-bold ${statusInfo.bg}`}>
                        {statusInfo.label}
                      </span>
                      <span className="text-[11px] text-slate-500 font-medium">{b.plan_count} lịch trình</span>
                    </div>
                  </Link>
                );
              })}
            </div>
          )}
        </div>
      </div>
    </div>
  );
}
