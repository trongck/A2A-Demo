"use client";
import React, { useEffect, useState, useCallback } from "react";
import Link from "next/link";
import { useAdminAuth } from "../layout";
import { getApiBase } from "../config";

interface Stats {
  total_sessions: number;
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

interface CrowdOverview {
  total_attractions: number;
  open_count: number;
  maintenance_count: number;
  closed_count: number;
  unknown_count: number;
  zones: ZoneData[];
}

const CROWD_BADGES: Record<string, { bg: string; text: string; label: string }> = {
  low: { bg: "bg-emerald-50 border-emerald-200", text: "text-emerald-700", label: "Vắng" },
  medium: { bg: "bg-amber-50 border-amber-200", text: "text-amber-700", label: "Bình thường" },
  high: { bg: "bg-rose-50 border-rose-200", text: "text-rose-700", label: "Đông đúc" },
  unknown: { bg: "bg-slate-50 border-slate-200", text: "text-slate-600", label: "Chưa rõ" },
};

function StatCard({ label, value, accentColor }: { label: string; value: number; accentColor: string }) {
  return (
    <div className={`bg-white border border-slate-200/80 shadow-xs rounded-2xl p-4 hover:shadow-sm transition-all border-l-4 ${accentColor}`}>
      <p className="text-2xl lg:text-3xl font-extrabold text-slate-900 tracking-tight">{value}</p>
      <p className="text-[11px] font-bold text-slate-500 mt-1 uppercase tracking-wider">{label}</p>
    </div>
  );
}

export default function DashboardPage() {
  const { token } = useAdminAuth();
  const [stats, setStats] = useState<Stats | null>(null);
  const [crowd, setCrowd] = useState<CrowdOverview | null>(null);
  const [lastRefresh, setLastRefresh] = useState<Date | null>(null);

  const fetchData = useCallback(async () => {
    const effectiveToken = token || (typeof window !== "undefined" ? localStorage.getItem("admin_token") : null);
    if (!effectiveToken) return;

    const authHeader: Record<string, string> = { Authorization: `Bearer ${effectiveToken}` };
    const apiBase = getApiBase();

    try {
      const [statsRes, crowdRes] = await Promise.all([
        fetch(`${apiBase}/admin/bookings/stats`, { headers: authHeader }),
        fetch(`${apiBase}/admin/crowd/overview`, { headers: authHeader }),
      ]);
      if (statsRes.ok) setStats(await statsRes.json());
      if (crowdRes.ok) setCrowd(await crowdRes.json());
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

  const allAttractions = crowd?.zones?.flatMap((z) => z.attractions) ?? [];

  return (
    <div className="h-full flex flex-col gap-4 overflow-hidden">
      {/* Tiêu đề & Làm mới */}
      <div className="flex items-center justify-between gap-4 shrink-0">
        <div>
          <h2 className="text-xl lg:text-2xl font-black text-slate-900 tracking-tight">
            Tổng quan hệ thống V-AI
          </h2>
          <p className="text-xs text-slate-500 font-medium">
            Hệ thống điều phối du lịch VinWonders Nha Trang • Cập nhật tự động mỗi 30 giây
          </p>
        </div>
        <div className="flex items-center gap-3">
          {lastRefresh && (
            <span className="text-xs text-slate-500 font-medium hidden sm:inline">
              Cập nhật: {lastRefresh.toLocaleTimeString("vi-VN")}
            </span>
          )}
          <button
            type="button"
            onClick={fetchData}
            className="px-3.5 py-1.5 bg-blue-600 hover:bg-blue-700 active:bg-blue-800 text-white text-xs font-bold rounded-xl transition-all shadow-xs cursor-pointer"
          >
            Làm mới
          </button>
        </div>
      </div>

      {/* 4 Thẻ chỉ số chính */}
      <div className="grid grid-cols-2 lg:grid-cols-4 gap-3.5 shrink-0">
        <StatCard
          label="Tổng phiên tư vấn"
          value={stats?.total_sessions ?? 0}
          accentColor="border-blue-600"
        />
        <StatCard
          label="Lịch trình đã lập"
          value={stats?.total_plans ?? 0}
          accentColor="border-teal-600"
        />
        <StatCard
          label="Điểm đang mở cửa"
          value={crowd?.open_count ?? 0}
          accentColor="border-emerald-600"
        />
        <StatCard
          label="Bảo trì / Tạm dừng"
          value={(crowd?.maintenance_count ?? 0) + (crowd?.closed_count ?? 0)}
          accentColor="border-amber-500"
        />
      </div>

      {/* Vùng nội dung 2 cột khớp 1 màn hình */}
      <div className="flex-1 grid grid-cols-1 lg:grid-cols-3 gap-4 min-h-0 overflow-hidden">
        {/* Cột trái (2/3): Mật độ các điểm vui chơi (cuộn nội bộ) */}
        <div className="lg:col-span-2 bg-white border border-slate-200/80 rounded-2xl p-4 shadow-xs flex flex-col min-h-0 overflow-hidden">
          <div className="flex items-center justify-between mb-3 shrink-0">
            <div>
              <h3 className="font-extrabold text-slate-900 text-sm">
                Mật độ các điểm vui chơi ({allAttractions.length} điểm)
              </h3>
              <p className="text-[11px] text-slate-500">Giám sát công suất và thời gian chờ theo thời gian thực</p>
            </div>
            <Link
              href="/admin/crowd"
              className="text-xs font-bold text-blue-600 hover:text-blue-700 transition-colors"
            >
              Mở bản đồ mật độ →
            </Link>
          </div>

          {/* Danh sách cuộn nội bộ */}
          <div className="flex-1 overflow-y-auto pr-1">
            <div className="grid grid-cols-1 sm:grid-cols-2 xl:grid-cols-3 gap-2.5">
              {allAttractions.map((a) => {
                const badge = CROWD_BADGES[a.crowd_level] ?? CROWD_BADGES.unknown;
                return (
                  <div
                    key={a.service_id}
                    className="bg-slate-50/90 rounded-xl p-3 border border-slate-200/70 hover:border-slate-300 hover:bg-slate-100/70 transition-all"
                  >
                    <p className="text-xs text-slate-800 font-bold leading-tight truncate">
                      {a.name}
                    </p>
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
          </div>

          {/* Chú giải mức độ */}
          <div className="flex flex-wrap items-center gap-4 mt-3 pt-3 border-t border-slate-100 text-[11px] shrink-0">
            <span className="font-bold text-slate-500">Mức độ:</span>
            <span className="text-emerald-700 font-semibold">• Vắng (&lt; 40%)</span>
            <span className="text-amber-700 font-semibold">• Bình thường (40 - 70%)</span>
            <span className="text-rose-700 font-semibold">• Đông đúc (&gt; 70%)</span>
          </div>
        </div>

        {/* Cột phải (1/3): Trạng thái vận hành & Phím tắt */}
        <div className="bg-white border border-slate-200/80 rounded-2xl p-4 shadow-xs flex flex-col justify-between overflow-hidden">
          <div>
            <h3 className="font-extrabold text-slate-900 text-sm mb-3">
              Trạng thái &amp; Điều phối
            </h3>

            <div className="space-y-2.5 mb-4">
              <div className="flex items-center justify-between p-2.5 rounded-xl bg-slate-50 border border-slate-200/60 text-xs">
                <span className="text-slate-600 font-medium">Tổng số điểm tham quan</span>
                <span className="font-bold font-mono text-slate-900">{crowd?.total_attractions ?? 0}</span>
              </div>
              <div className="flex items-center justify-between p-2.5 rounded-xl bg-emerald-50/70 border border-emerald-200/60 text-xs">
                <span className="text-emerald-800 font-medium">Đang mở cửa đón khách</span>
                <span className="font-bold font-mono text-emerald-800">{crowd?.open_count ?? 0}</span>
              </div>
              <div className="flex items-center justify-between p-2.5 rounded-xl bg-amber-50/70 border border-amber-200/60 text-xs">
                <span className="text-amber-800 font-medium">Đang bảo trì định kỳ</span>
                <span className="font-bold font-mono text-amber-800">{crowd?.maintenance_count ?? 0}</span>
              </div>
              <div className="flex items-center justify-between p-2.5 rounded-xl bg-rose-50/70 border border-rose-200/60 text-xs">
                <span className="text-rose-800 font-medium">Tạm dừng hoạt động</span>
                <span className="font-bold font-mono text-rose-800">{crowd?.closed_count ?? 0}</span>
              </div>
            </div>
          </div>

          {/* Phím tắt công cụ quản trị */}
          <div className="pt-3 border-t border-slate-100 space-y-2">
            <Link
              href="/admin/crowd"
              className="w-full flex items-center justify-between px-3.5 py-2.5 rounded-xl bg-teal-50 hover:bg-teal-100/80 text-teal-800 text-xs font-bold border border-teal-200 transition-colors"
            >
              <span>Bản đồ mật độ Mapbox</span>
              <span>→</span>
            </Link>
            <Link
              href="/admin/map"
              className="w-full flex items-center justify-between px-3.5 py-2.5 rounded-xl bg-blue-50 hover:bg-blue-100/80 text-blue-700 text-xs font-bold border border-blue-200 transition-colors"
            >
              <span>Bản đồ POI &amp; Tìm đường ngắn nhất</span>
              <span>→</span>
            </Link>
          </div>
        </div>
      </div>
    </div>
  );
}
