"use client";
import React, { useEffect, useState, useCallback } from "react";
import { useAdminAuth } from "../layout";
import { getApiBase } from "../config";

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
  data_quality: string;
  x_m: number;
  y_m: number;
}

interface ZoneData {
  zone_id: string;
  zone_name: string;
  attractions: Attraction[];
}

interface OverviewData {
  observed_at: string;
  total_attractions: number;
  open_count: number;
  maintenance_count: number;
  closed_count: number;
  zones: ZoneData[];
}

const CROWD_DOT: Record<string, string> = {
  low: "#10b981",
  medium: "#f59e0b",
  high: "#ef4444",
  unknown: "#94a3b8",
};

const CROWD_INFO: Record<string, { bg: string; text: string; label: string }> = {
  low: { bg: "bg-emerald-50 border-emerald-200", text: "text-emerald-700", label: "Vắng" },
  medium: { bg: "bg-amber-50 border-amber-200", text: "text-amber-700", label: "Bình thường" },
  high: { bg: "bg-rose-50 border-rose-200", text: "text-rose-700", label: "Đông đúc" },
  unknown: { bg: "bg-slate-50 border-slate-200", text: "text-slate-600", label: "Chưa rõ" },
};

const STATUS_TEXT: Record<string, { label: string; bg: string; text: string }> = {
  open: { label: "Đang mở cửa", bg: "bg-emerald-50 border-emerald-200", text: "text-emerald-700" },
  maintenance: { label: "Đang bảo trì", bg: "bg-amber-50 border-amber-200", text: "text-amber-700" },
  temporarily_closed: { label: "Tạm dừng", bg: "bg-rose-50 border-rose-200", text: "text-rose-700" },
  closed: { label: "Đã đóng cửa", bg: "bg-slate-100 border-slate-200", text: "text-slate-600" },
};

function MapSVG({
  zones,
  selected,
  onSelect,
}: {
  zones: ZoneData[];
  selected: string | null;
  onSelect: (id: string) => void;
}) {
  const allAttrs = zones.flatMap((z) => z.attractions);
  const maxX = Math.max(...allAttrs.map((a) => a.x_m), 1280);
  const maxY = Math.max(...allAttrs.map((a) => a.y_m), 960);
  const W = 560;
  const H = 420;
  const sx = W / (maxX + 160);
  const sy = H / (maxY + 160);
  const scale = Math.min(sx, sy);
  const px = (x: number) => (x + 80) * scale;
  const py = (y: number) => (y + 80) * scale;

  return (
    <svg width={W} height={H} className="w-full h-auto rounded-xl bg-slate-50 border border-slate-200">
      {/* Khung viền các khu vực */}
      {zones.map((z) => {
        const attrs = z.attractions;
        if (!attrs.length) return null;
        const xs = attrs.map((a) => a.x_m);
        const ys = attrs.map((a) => a.y_m);
        const x1 = Math.min(...xs) - 60;
        const y1 = Math.min(...ys) - 60;
        const x2 = Math.max(...xs) + 60;
        const y2 = Math.max(...ys) + 60;
        return (
          <rect
            key={z.zone_id}
            x={px(x1)}
            y={py(y1)}
            width={(x2 - x1) * scale}
            height={(y2 - y1) * scale}
            rx={10}
            fill="rgba(241,245,249,0.8)"
            stroke="#cbd5e1"
            strokeWidth={1}
          />
        );
      })}
      {/* Tọa độ các điểm POI */}
      {allAttrs.map((a) => {
        const cx = px(a.x_m);
        const cy = py(a.y_m);
        const color = CROWD_DOT[a.crowd_level] ?? "#94a3b8";
        const isSelected = selected === a.service_id;
        return (
          <g key={a.service_id} onClick={() => onSelect(a.service_id)} className="cursor-pointer">
            {isSelected && <circle cx={cx} cy={cy} r={20} fill={color} opacity={0.25} />}
            <circle
              cx={cx}
              cy={cy}
              r={isSelected ? 10 : 7}
              fill={color}
              opacity={a.operating_status === "open" ? 1 : 0.4}
              stroke={isSelected ? "#1e293b" : "#ffffff"}
              strokeWidth={2}
            />
            <text
              x={cx}
              y={cy + 18}
              textAnchor="middle"
              fontSize={9}
              fontWeight="600"
              fill="#334155"
              className="select-none pointer-events-none"
            >
              {a.name.length > 12 ? a.name.slice(0, 12) + "…" : a.name}
            </text>
          </g>
        );
      })}
    </svg>
  );
}

export default function CrowdPage() {
  const { token } = useAdminAuth();
  const [data, setData] = useState<OverviewData | null>(null);
  const [selected, setSelected] = useState<string | null>(null);
  const [updateSid, setUpdateSid] = useState("");
  const [updatePeople, setUpdatePeople] = useState("");
  const [updateWait, setUpdateWait] = useState("");
  const [updating, setUpdating] = useState(false);
  const [toast, setToast] = useState<string | null>(null);

  const getEffectiveToken = () =>
    token || (typeof window !== "undefined" ? localStorage.getItem("admin_token") : null);

  const fetchData = useCallback(async () => {
    const curToken = getEffectiveToken();
    if (!curToken) return;
    try {
      const apiBase = getApiBase();
      const r = await fetch(`${apiBase}/admin/crowd/overview`, {
        headers: { Authorization: `Bearer ${curToken}` },
      });
      if (r.ok) setData(await r.json());
    } catch (err) {
      console.warn("Crowd fetch error:", err);
    }
  }, [token]);

  useEffect(() => {
    fetchData();
    const id = setInterval(fetchData, 30000);
    return () => clearInterval(id);
  }, [fetchData]);

  const selectedAttr = data?.zones.flatMap((z) => z.attractions).find((a) => a.service_id === selected);

  async function handleUpdate() {
    const curToken = getEffectiveToken();
    if (!curToken) return;
    if (!updateSid || !updatePeople) {
      setToast("Vui lòng nhập đầy đủ thông tin.");
      return;
    }
    setUpdating(true);
    try {
      const apiBase = getApiBase();
      const r = await fetch(`${apiBase}/admin/crowd/${updateSid}`, {
        method: "PATCH",
        headers: { Authorization: `Bearer ${curToken}`, "Content-Type": "application/json" },
        body: JSON.stringify({
          current_people: parseInt(updatePeople),
          wait_minutes: updateWait ? parseInt(updateWait) : null,
        }),
      });
      if (r.ok) {
        setToast("Cập nhật mật độ thành công!");
        await fetchData();
      } else {
        const d = await r.json();
        setToast(d.detail ?? "Lỗi cập nhật dữ liệu.");
      }
    } catch {
      setToast("Lỗi kết nối máy chủ.");
    } finally {
      setUpdating(false);
      setTimeout(() => setToast(null), 3000);
    }
  }

  const allAttractions = data?.zones.flatMap((z) => z.attractions) ?? [];

  return (
    <div className="space-y-6">
      {toast && (
        <div className="fixed top-6 right-6 z-50 px-5 py-3 rounded-xl bg-blue-600 text-white text-xs font-bold shadow-lg">
          {toast}
        </div>
      )}

      {/* Tiêu đề & Làm mới */}
      <div className="flex flex-wrap items-center justify-between gap-4">
        <div>
          <h2 className="text-2xl font-black text-slate-900 tracking-tight">Theo dõi mật độ khu vui chơi</h2>
          <p className="text-xs text-slate-500 font-medium mt-0.5">Tự động làm mới dữ liệu mỗi 30 giây</p>
        </div>
        <button
          onClick={fetchData}
          className="px-4 py-2 bg-blue-600 hover:bg-blue-700 text-white text-xs font-bold rounded-xl transition-all shadow-xs cursor-pointer"
        >
          Làm mới ngay
        </button>
      </div>

      {/* Thẻ trạng thái hoạt động */}
      {data && (
        <div className="grid grid-cols-1 sm:grid-cols-3 gap-4">
          <div className="bg-white border border-slate-200/80 rounded-2xl p-4 shadow-xs border-l-4 border-emerald-500">
            <p className="text-2xl font-black text-slate-900">{data.open_count}</p>
            <p className="text-xs font-bold text-slate-500 mt-1 uppercase tracking-wider">Đang mở cửa</p>
          </div>
          <div className="bg-white border border-slate-200/80 rounded-2xl p-4 shadow-xs border-l-4 border-amber-500">
            <p className="text-2xl font-black text-slate-900">{data.maintenance_count}</p>
            <p className="text-xs font-bold text-slate-500 mt-1 uppercase tracking-wider">Đang bảo trì</p>
          </div>
          <div className="bg-white border border-slate-200/80 rounded-2xl p-4 shadow-xs border-l-4 border-slate-400">
            <p className="text-2xl font-black text-slate-900">{data.closed_count}</p>
            <p className="text-xs font-bold text-slate-500 mt-1 uppercase tracking-wider">Đã đóng cửa</p>
          </div>
        </div>
      )}

      <div className="grid grid-cols-1 xl:grid-cols-3 gap-6">
        {/* Bản đồ trực quan */}
        <div className="xl:col-span-2 space-y-4">
          <div className="bg-white border border-slate-200/80 rounded-2xl p-6 shadow-xs">
            <h3 className="font-extrabold text-slate-900 text-base mb-4">Bản đồ mật độ trực tiếp</h3>
            {data ? (
              <MapSVG zones={data.zones} selected={selected} onSelect={setSelected} />
            ) : (
              <div className="h-[420px] bg-slate-100 rounded-xl animate-pulse" />
            )}
            <div className="flex flex-wrap items-center gap-5 mt-4 pt-4 border-t border-slate-100">
              {[
                ["low", "Thấp / Vắng", "#10b981"],
                ["medium", "Bình thường", "#f59e0b"],
                ["high", "Đông đúc", "#ef4444"],
                ["unknown", "Chưa rõ", "#94a3b8"],
              ].map(([k, l, c]) => (
                <div key={k} className="flex items-center gap-2">
                  <div className="w-3 h-3 rounded-full" style={{ background: c as string }} />
                  <span className="text-xs font-semibold text-slate-600">{l as string}</span>
                </div>
              ))}
            </div>
          </div>

          {/* Chi tiết điểm được chọn */}
          {selectedAttr && (
            <div className="bg-white border border-slate-200/80 rounded-2xl p-6 shadow-xs">
              <div className="flex items-center justify-between mb-4">
                <h4 className="font-extrabold text-slate-900 text-base">{selectedAttr.name}</h4>
                <span
                  className={`text-xs font-bold px-3 py-1 rounded-full border ${
                    STATUS_TEXT[selectedAttr.operating_status]?.bg ?? "bg-slate-50 border-slate-200"
                  } ${STATUS_TEXT[selectedAttr.operating_status]?.text ?? "text-slate-600"}`}
                >
                  {STATUS_TEXT[selectedAttr.operating_status]?.label ?? selectedAttr.operating_status}
                </span>
              </div>
              <div className="grid grid-cols-3 gap-4 text-xs">
                <div className="bg-slate-50 p-3 rounded-xl border border-slate-200/60">
                  <p className="text-slate-500 font-medium">Khách hiện tại</p>
                  <p className="font-black text-slate-900 text-lg mt-0.5">
                    {selectedAttr.current_people !== null ? `${selectedAttr.current_people} người` : "Chưa rõ"}
                  </p>
                </div>
                <div className="bg-slate-50 p-3 rounded-xl border border-slate-200/60">
                  <p className="text-slate-500 font-medium">Sức chứa tối đa</p>
                  <p className="font-black text-slate-900 text-lg mt-0.5">{selectedAttr.capacity} người</p>
                </div>
                <div className="bg-slate-50 p-3 rounded-xl border border-slate-200/60">
                  <p className="text-slate-500 font-medium">Thời gian chờ</p>
                  <p className="font-black text-slate-900 text-lg mt-0.5">
                    {selectedAttr.wait_minutes !== null ? `${selectedAttr.wait_minutes} phút` : "Không phải chờ"}
                  </p>
                </div>
              </div>
              {selectedAttr.occupancy_rate !== null && (
                <div className="mt-4">
                  <div className="flex justify-between text-xs font-bold text-slate-600 mb-1.5">
                    <span>Tỷ lệ lấp đầy</span>
                    <span>{(selectedAttr.occupancy_rate * 100).toFixed(0)}%</span>
                  </div>
                  <div className="h-2.5 bg-slate-100 rounded-full overflow-hidden">
                    <div
                      className="h-full rounded-full transition-all"
                      style={{
                        width: `${Math.min(100, selectedAttr.occupancy_rate * 100)}%`,
                        background: CROWD_DOT[selectedAttr.crowd_level] ?? CROWD_DOT.unknown,
                      }}
                    />
                  </div>
                </div>
              )}
              <button
                onClick={() => {
                  setUpdateSid(selectedAttr.service_id);
                  setUpdatePeople(String(selectedAttr.current_people ?? 0));
                  setUpdateWait(String(selectedAttr.wait_minutes ?? 0));
                }}
                className="mt-4 text-xs font-bold text-blue-600 hover:text-blue-800 transition-colors cursor-pointer"
              >
                Cập nhật thông số cho điểm này →
              </button>
            </div>
          )}
        </div>

        {/* Cột phải: Form cập nhật và danh sách khu vực */}
        <div className="space-y-6">
          {/* Form cập nhật dữ liệu thử nghiệm */}
          <div className="bg-white border border-slate-200/80 rounded-2xl p-6 shadow-xs">
            <h3 className="font-extrabold text-slate-900 text-base mb-4">Cập nhật mật độ (Thử nghiệm)</h3>
            <div className="space-y-4">
              <div>
                <label className="block text-xs font-bold text-slate-700 mb-1.5">Điểm vui chơi</label>
                <select
                  value={updateSid}
                  onChange={(e) => setUpdateSid(e.target.value)}
                  className="w-full px-3.5 py-2.5 bg-white border border-slate-300 rounded-xl text-slate-900 text-xs font-medium outline-none focus:border-blue-600 focus:ring-1 focus:ring-blue-600"
                >
                  <option value="">-- Chọn điểm vui chơi --</option>
                  {allAttractions.map((a) => (
                    <option key={a.service_id} value={a.service_id}>
                      {a.name}
                    </option>
                  ))}
                </select>
              </div>
              <div>
                <label className="block text-xs font-bold text-slate-700 mb-1.5">Số khách hiện tại</label>
                <input
                  type="number"
                  min={0}
                  value={updatePeople}
                  onChange={(e) => setUpdatePeople(e.target.value)}
                  placeholder="Ví dụ: 80"
                  className="w-full px-3.5 py-2.5 bg-white border border-slate-300 rounded-xl text-slate-900 text-xs font-medium outline-none focus:border-blue-600 focus:ring-1 focus:ring-blue-600"
                />
              </div>
              <div>
                <label className="block text-xs font-bold text-slate-700 mb-1.5">Thời gian chờ (phút)</label>
                <input
                  type="number"
                  min={0}
                  value={updateWait}
                  onChange={(e) => setUpdateWait(e.target.value)}
                  placeholder="Ví dụ: 15"
                  className="w-full px-3.5 py-2.5 bg-white border border-slate-300 rounded-xl text-slate-900 text-xs font-medium outline-none focus:border-blue-600 focus:ring-1 focus:ring-blue-600"
                />
              </div>
              <button
                onClick={handleUpdate}
                disabled={updating}
                className="w-full py-2.5 bg-blue-600 hover:bg-blue-700 disabled:opacity-50 text-white text-xs font-bold rounded-xl transition-all shadow-xs cursor-pointer"
              >
                {updating ? "Đang cập nhật..." : "Cập nhật dữ liệu"}
              </button>
            </div>
          </div>

          {/* Danh sách theo phân khu */}
          {data?.zones.map((z) => (
            <div key={z.zone_id} className="bg-white border border-slate-200/80 rounded-2xl overflow-hidden shadow-xs">
              <div className="px-5 py-3 border-b border-slate-100 bg-slate-50/80">
                <h4 className="text-xs font-extrabold text-slate-800 uppercase tracking-wider">{z.zone_name}</h4>
              </div>
              <div className="divide-y divide-slate-100">
                {z.attractions.map((a) => (
                  <button
                    key={a.service_id}
                    onClick={() => setSelected(a.service_id)}
                    className={`w-full flex items-center gap-3 px-5 py-3 hover:bg-slate-50 transition-all text-left cursor-pointer ${
                      selected === a.service_id ? "bg-blue-50/80" : ""
                    }`}
                  >
                    <div
                      className="w-2.5 h-2.5 rounded-full shrink-0"
                      style={{ background: CROWD_DOT[a.crowd_level] ?? CROWD_DOT.unknown }}
                    />
                    <div className="flex-1 min-w-0">
                      <p className="text-xs font-bold text-slate-800 truncate">{a.name}</p>
                      <p className="text-xs text-slate-500 font-medium">
                        {a.current_people !== null ? `${a.current_people}/${a.capacity} khách` : "Chưa rõ"}{" "}
                        {a.indoor ? "[Trong nhà]" : ""}
                      </p>
                    </div>
                    {a.wait_minutes !== null && a.wait_minutes > 0 && (
                      <span className="text-xs font-bold text-amber-700 bg-amber-50 border border-amber-200 px-2 py-0.5 rounded-full shrink-0">
                        {a.wait_minutes} phút chờ
                      </span>
                    )}
                  </button>
                ))}
              </div>
            </div>
          ))}
        </div>
      </div>
    </div>
  );
}
