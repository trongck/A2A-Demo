"use client";
import React, { useEffect, useState, useRef, useCallback } from "react";
import { useAdminAuth } from "../layout";
import { getApiBase } from "../config";
import { DOMAIN_CONFIG } from "../map/page";

interface Attraction {
  service_id: string;
  name: string;
  category: string;
  indoor: boolean;
  operating_status: string;
  current_people: number | null;
  capacity: number | null;
  occupancy_rate: number | null;
  crowd_level: string;
  wait_minutes: number | null;
  data_quality: string;
  lat?: number;
  lng?: number;
  zone_id: string;
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
  unknown_count: number;
  zones: ZoneData[];
}

const CROWD_COLORS: Record<string, { hex: string; bg: string; text: string; border: string; label: string }> = {
  low: { hex: "#10b981", bg: "bg-emerald-50", text: "text-emerald-700", border: "border-emerald-200", label: "Vắng" },
  medium: { hex: "#f59e0b", bg: "bg-amber-50", text: "text-amber-700", border: "border-amber-200", label: "Bình thường" },
  high: { hex: "#ef4444", bg: "bg-rose-50", text: "text-rose-700", border: "border-rose-200", label: "Đông đúc" },
  unknown: { hex: "#94a3b8", bg: "bg-slate-50", text: "text-slate-600", border: "border-slate-200", label: "Đóng / Chưa rõ" },
};

const STATUS_TEXT: Record<string, { label: string; text: string }> = {
  open: { label: "Mở cửa", text: "text-emerald-700" },
  maintenance: { label: "Bảo trì", text: "text-amber-700" },
  temporarily_closed: { label: "Tạm dừng", text: "text-rose-700" },
  closed: { label: "Đóng cửa", text: "text-slate-600" },
  unknown: { label: "Chưa rõ", text: "text-slate-500" },
};

export default function CrowdPage() {
  const { token } = useAdminAuth();
  const mapContainerRef = useRef<HTMLDivElement>(null);
  const mapRef = useRef<any>(null);
  const markersRef = useRef<Record<string, { marker: any; element: HTMLElement; category: string; crowd_level: string }>>({});

  const [data, setData] = useState<OverviewData | null>(null);
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [filterCrowd, setFilterCrowd] = useState<string>("all");
  const [filterCategory, setFilterCategory] = useState<string>("all");
  const [searchQuery, setSearchQuery] = useState<string>("");
  const [loading, setLoading] = useState<boolean>(true);
  const [lastRefresh, setLastRefresh] = useState<Date | null>(null);

  const fetchOverview = useCallback(async () => {
    const effectiveToken = token || (typeof window !== "undefined" ? localStorage.getItem("admin_token") : null);
    if (!effectiveToken) return;

    try {
      const apiBase = getApiBase();
      const res = await fetch(`${apiBase}/admin/crowd/overview`, {
        headers: { Authorization: `Bearer ${effectiveToken}` },
      });
      if (res.ok) {
        const d: OverviewData = await res.json();
        setData(d);
        setLastRefresh(new Date());
      }
    } catch (err) {
      console.warn("Crowd fetch error:", err);
    } finally {
      setLoading(false);
    }
  }, [token]);

  useEffect(() => {
    fetchOverview();
    const id = setInterval(fetchOverview, 30000);
    return () => clearInterval(id);
  }, [fetchOverview]);

  const allAttractions = data?.zones.flatMap((z) => z.attractions) ?? [];

  // Khởi tạo Mapbox GL JS map
  useEffect(() => {
    if (typeof window === "undefined" || !mapContainerRef.current) return;
    const mbToken = process.env.NEXT_PUBLIC_MAPBOX_TOKEN;
    if (!mbToken) return;

    let cancelled = false;

    async function initMap() {
      const mapboxgl = (await import("mapbox-gl")).default;
      if (cancelled || !mapContainerRef.current) return;

      if (mapRef.current) {
        try {
          mapRef.current.remove();
        } catch (_) {}
        mapRef.current = null;
      }

      mapboxgl.accessToken = mbToken;

      const map = new mapboxgl.Map({
        container: mapContainerRef.current!,
        style: "mapbox://styles/mapbox/streets-v12",
        center: [109.243, 12.218], // VinWonders Nha Trang
        zoom: 15.3,
        attributionControl: false,
      });

      mapRef.current = map;
      map.addControl(new mapboxgl.NavigationControl({ showCompass: true }), "top-right");

      map.on("load", () => {
        if (cancelled) return;
        map.resize();
      });
    }

    initMap();

    return () => {
      cancelled = true;
      if (mapRef.current) {
        try {
          mapRef.current.remove();
        } catch (_) {}
        mapRef.current = null;
      }
    };
  }, []);

  // Lựa chọn và đồng bộ POI giữa bản đồ và danh sách
  const selectPoi = useCallback((attr: Attraction, fly: boolean = true) => {
    setSelectedId(attr.service_id);

    // Cuộn danh sách bên phải tới thẻ POI tương ứng
    const cardEl = document.getElementById(`poi-card-${attr.service_id}`);
    if (cardEl) {
      cardEl.scrollIntoView({ behavior: "smooth", block: "nearest" });
    }

    // Di chuyển bản đồ và bật popup
    if (fly && mapRef.current && attr.lat && attr.lng) {
      mapRef.current.flyTo({
        center: [attr.lng, attr.lat],
        zoom: 17,
        duration: 700,
      });
      const item = markersRef.current[attr.service_id];
      if (item && !item.marker.getPopup()?.isOpen()) {
        item.marker.togglePopup();
      }
    }
  }, []);

  // Cập nhật Markers Google Maps Style trên Mapbox khi có dữ liệu attractions
  useEffect(() => {
    if (!mapRef.current || allAttractions.length === 0) return;

    const map = mapRef.current;
    import("mapbox-gl").then(({ default: mapboxgl }) => {
      // Xóa markers cũ
      Object.values(markersRef.current).forEach((m) => m.marker.remove());
      markersRef.current = {};

      allAttractions.forEach((attr) => {
        if (!attr.lat || !attr.lng) return;

        const cat = attr.category || "attraction";
        const domain = DOMAIN_CONFIG[cat] ?? DOMAIN_CONFIG.attraction;
        const crowd = CROWD_COLORS[attr.crowd_level] ?? CROWD_COLORS.unknown;
        const status = STATUS_TEXT[attr.operating_status] ?? STATUS_TEXT.unknown;

        // Container gốc định vị bởi Mapbox (KHÔNG dùng scale/transition để tránh xung đột với translate)
        const el = document.createElement("div");
        el.className = "cursor-pointer select-none";
        el.style.pointerEvents = "auto";

        // Khung wrapper bên trong: Thực hiện hover scale mượt mà KHÔNG bị nháy
        const innerWrapper = document.createElement("div");
        innerWrapper.className = "flex flex-col items-center group transition-transform duration-150 ease-out hover:scale-120";
        innerWrapper.style.transformOrigin = "bottom center";

        // Khung pin chính theo phong cách Google Maps (giọt nước bo góc quay -45 độ)
        const pin = document.createElement("div");
        pin.style.cssText = `
          width: 26px;
          height: 26px;
          background-color: ${domain.color};
          color: #ffffff;
          border: 2px solid #ffffff;
          border-radius: 50% 50% 50% 0;
          transform: rotate(-45deg);
          display: flex;
          align-items: center;
          justify-content: center;
          box-shadow: 0 3px 8px rgba(0,0,0,0.35);
          position: relative;
        `;

        // Icon SVG của Domain nằm ngay ngắn bên trong pin
        const iconWrap = document.createElement("div");
        iconWrap.style.cssText = `
          transform: rotate(45deg);
          display: flex;
          align-items: center;
          justify-content: center;
        `;
        iconWrap.innerHTML = domain.svg;
        pin.appendChild(iconWrap);

        // Huy hiệu mật độ / số phút chờ đính góc trên của pin
        const crowdBadge = document.createElement("div");
        crowdBadge.style.cssText = `
          position: absolute;
          top: -6px;
          right: -6px;
          background-color: ${crowd.hex};
          color: #ffffff;
          border: 1.5px solid #ffffff;
          border-radius: 10px;
          font-size: 8.5px;
          font-weight: 800;
          padding: 1px 4px;
          transform: rotate(45deg);
          box-shadow: 0 1px 4px rgba(0,0,0,0.3);
          line-height: 1;
        `;
        crowdBadge.textContent = attr.wait_minutes ? `${attr.wait_minutes}p` : "•";
        pin.appendChild(crowdBadge);

        // Nhãn tên POI hiển thị trực tiếp bên dưới ghim (có viền trắng halo chống lóa)
        const label = document.createElement("div");
        label.style.cssText = `
          font-size: 10px;
          font-weight: 700;
          color: #0f172a;
          text-shadow: 0 0 2px #fff, 0 0 3px #fff, 0 0 4px #fff, 1px 1px 2px #fff, -1px -1px 2px #fff;
          max-width: 95px;
          overflow: hidden;
          text-overflow: ellipsis;
          white-space: nowrap;
          margin-top: 3px;
          text-align: center;
          line-height: 1.15;
          pointer-events: none;
        `;
        label.textContent = attr.name;

        innerWrapper.appendChild(pin);
        innerWrapper.appendChild(label);
        el.appendChild(innerWrapper);

        // Popup hiển thị chi tiết thông tin POI khi click vào
        const popupContent = [
          '<div style="font-family: inherit; font-size: 12px; min-width: 200px; padding: 4px;">',
          '<div style="display: flex; align-items: center; justify-content: space-between; gap: 6px; margin-bottom: 5px;">',
          `<span style="font-size: 10px; font-weight: 700; padding: 2px 7px; border-radius: 6px; background-color: ${domain.color}15; color: ${domain.color}; border: 1px solid ${domain.color}40;">`,
          `${domain.iconText} ${domain.label}`,
          "</span>",
          `<span style="font-size: 10px; font-weight: 700; padding: 2px 6px; border-radius: 6px; background-color: ${crowd.hex}15; color: ${crowd.hex}; border: 1px solid ${crowd.hex}40;">`,
          `${crowd.label}`,
          "</span>",
          "</div>",
          `<div style="font-weight: 800; color: #0f172a; font-size: 13.5px; line-height: 1.3; margin-bottom: 4px;">${attr.name}</div>`,
          `<div style="font-size: 11px; margin-bottom: 5px; color: ${attr.operating_status === "open" ? "#059669" : "#dc2626"}; font-weight: 600;">Trạng thái: ${status.label}</div>`,
          attr.current_people !== null && attr.capacity
            ? `<div style="font-size: 11px; color: #475569; margin-bottom: 2px;">Lượng khách: <b>${attr.current_people}/${attr.capacity}</b> (${Math.round((attr.occupancy_rate || 0) * 100)}%)</div>`
            : "",
          attr.wait_minutes !== null
            ? `<div style="font-size: 11.5px; color: #0f766e; font-weight: 700; margin-top: 3px; padding-top: 3px; border-top: 1px dashed #e2e8f0;">Thời gian chờ: ${attr.wait_minutes} phút</div>`
            : "",
          "</div>",
        ].join("");

        const popup = new mapboxgl.Popup({ offset: 16, closeButton: true, maxWidth: "250px" }).setHTML(popupContent);

        const marker = new mapboxgl.Marker({ element: el, anchor: "bottom" })
          .setLngLat([attr.lng, attr.lat])
          .setPopup(popup)
          .addTo(map);

        el.addEventListener("click", () => {
          selectPoi(attr, false);
        });

        markersRef.current[attr.service_id] = { marker, element: el, category: cat, crowd_level: attr.crowd_level };
      });
    });
  }, [allAttractions, selectPoi]);

  // Bộ lọc cập nhật độ mờ hiển thị của markers trên Mapbox
  useEffect(() => {
    Object.values(markersRef.current).forEach(({ element, category, crowd_level }) => {
      const matchCat = filterCategory === "all" || category === filterCategory;
      const matchCrowd = filterCrowd === "all" || crowd_level === filterCrowd;

      if (matchCat && matchCrowd) {
        element.style.opacity = "1";
        element.style.filter = "none";
        element.style.pointerEvents = "auto";
      } else {
        element.style.opacity = "0.25";
        element.style.filter = "grayscale(60%)";
        element.style.pointerEvents = "auto";
      }
    });
  }, [filterCategory, filterCrowd]);

  // Lọc danh sách POI bên phải theo điều kiện
  const filteredAttractions = allAttractions.filter((a) => {
    if (filterCrowd !== "all" && a.crowd_level !== filterCrowd) return false;
    if (filterCategory !== "all" && a.category !== filterCategory) return false;
    if (searchQuery.trim()) {
      const q = searchQuery.toLowerCase();
      return a.name.toLowerCase().includes(q) || (a.category && a.category.toLowerCase().includes(q));
    }
    return true;
  });

  return (
    <div className="h-full flex flex-col gap-2.5 overflow-hidden">
      {/* Thanh tiêu đề & Tóm tắt số liệu */}
      <div className="flex flex-wrap items-center justify-between gap-3 shrink-0">
        <div>
          <h2 className="text-xl font-black text-slate-900 tracking-tight flex items-center gap-2">
            <span>Giám Sát Mật Độ &amp; Hàng Đợi Thời Gian Thực</span>
            <span className="text-[11px] font-bold px-2 py-0.5 rounded-full bg-emerald-50 text-emerald-700 border border-emerald-200">
              Live Mapbox
            </span>
          </h2>
          <p className="text-xs text-slate-500 font-medium">
            Phân loại Google Maps style với nhãn tên POI &amp; cảnh báo mật độ tức thời tại VinWonders Nha Trang
          </p>
        </div>

        {/* Thống kê nhanh */}
        <div className="flex items-center gap-2">
          {data && (
            <div className="flex items-center gap-2 bg-white px-3 py-1.5 rounded-xl border border-slate-200 shadow-2xs text-xs">
              <span className="font-semibold text-emerald-700 flex items-center gap-1">
                <span className="w-2 h-2 rounded-full bg-emerald-500" />
                {data.open_count} Mở
              </span>
              <span className="text-slate-300">|</span>
              <span className="font-semibold text-rose-700 flex items-center gap-1">
                <span className="w-2 h-2 rounded-full bg-rose-500" />
                {data.closed_count + data.maintenance_count} Tạm dừng
              </span>
              {lastRefresh && (
                <>
                  <span className="text-slate-300">|</span>
                  <span className="text-[10px] text-slate-400 font-mono">
                    Cập nhật: {lastRefresh.toLocaleTimeString("vi-VN")}
                  </span>
                </>
              )}
            </div>
          )}

          <button
            type="button"
            onClick={() => fetchOverview()}
            disabled={loading}
            className="text-xs font-semibold px-3 py-1.5 rounded-xl border border-slate-200 bg-white hover:bg-slate-50 text-slate-700 transition cursor-pointer shadow-2xs"
          >
            {loading ? "Đang tải..." : "Làm mới"}
          </button>
        </div>
      </div>

      {/* Thanh bộ lọc danh mục Google Maps Category Chips */}
      <div className="flex items-center gap-1.5 overflow-x-auto py-1 shrink-0 scrollbar-none">
        <button
          type="button"
          onClick={() => setFilterCategory("all")}
          className={`text-xs font-bold px-3 py-1.5 rounded-xl border transition cursor-pointer shrink-0 flex items-center gap-1.5 ${
            filterCategory === "all"
              ? "bg-slate-900 text-white border-slate-900 shadow-xs"
              : "bg-white text-slate-700 border-slate-200 hover:bg-slate-50"
          }`}
        >
          <span>Tất cả ({allAttractions.length})</span>
        </button>

        {Object.entries(DOMAIN_CONFIG).map(([key, cfg]) => {
          const count = allAttractions.filter((a) => (a.category || "attraction") === key).length;
          if (count === 0 && key !== "hub") return null;
          const isActive = filterCategory === key;
          return (
            <button
              key={key}
              type="button"
              onClick={() => setFilterCategory(isActive ? "all" : key)}
              className={`text-xs font-bold px-2.5 py-1.5 rounded-xl border transition cursor-pointer shrink-0 flex items-center gap-1.5 ${
                isActive
                  ? "bg-white border-slate-900 shadow-sm ring-1 ring-slate-900"
                  : "bg-white text-slate-700 border-slate-200 hover:bg-slate-50"
              }`}
            >
              <span
                className="w-2 h-2 rounded-full inline-block"
                style={{ backgroundColor: cfg.color }}
              />
              <span>{cfg.label}</span>
              <span className="text-[10px] text-slate-400 font-normal">({count})</span>
            </button>
          );
        })}
      </div>

      {/* Bố cục 2 cột cố định trong 1 màn hình duy nhất */}
      <div className="flex-1 flex flex-col lg:flex-row gap-3 overflow-hidden min-h-0">
        {/* Cột Trái: Bản đồ Mapbox GL */}
        <div className="flex-1 h-full min-h-[300px] rounded-2xl overflow-hidden border border-slate-200 shadow-xs relative bg-slate-100">
          <div ref={mapContainerRef} className="w-full h-full" />

          {/* Chú giải góc dưới bản đồ */}
          <div className="absolute bottom-3 left-3 bg-white/95 backdrop-blur-xs px-3 py-2 rounded-xl text-[11px] border border-slate-200 shadow-md flex flex-wrap items-center gap-2.5 max-w-[85%]">
            <span className="font-bold text-slate-700 text-[10px] uppercase tracking-wider mr-1">Mật độ:</span>
            <span className="flex items-center gap-1 font-semibold text-emerald-700 text-[10.5px]">
              <span className="w-2.5 h-2.5 rounded-full bg-emerald-500 inline-block" /> Vắng (&lt; 40%)
            </span>
            <span className="flex items-center gap-1 font-semibold text-amber-700 text-[10.5px]">
              <span className="w-2.5 h-2.5 rounded-full bg-amber-500 inline-block" /> Bình thường (40 - 70%)
            </span>
            <span className="flex items-center gap-1 font-semibold text-rose-700 text-[10.5px]">
              <span className="w-2.5 h-2.5 rounded-full bg-rose-500 inline-block" /> Đông đúc (&gt; 70%)
            </span>
          </div>
        </div>

        {/* Cột Phải: Bảng danh sách POI cuộn độc lập bên trong */}
        <div className="w-full lg:w-96 bg-white rounded-2xl border border-slate-200 shadow-xs flex flex-col overflow-hidden h-full shrink-0">
          {/* Header bảng điều khiển */}
          <div className="p-3.5 border-b border-slate-100 space-y-2.5 shrink-0 bg-slate-50/70">
            <div className="flex items-center justify-between">
              <span className="text-xs font-extrabold uppercase tracking-wider text-slate-800">
                Danh sách POI ({filteredAttractions.length})
              </span>
              <select
                value={filterCrowd}
                onChange={(e) => setFilterCrowd(e.target.value)}
                className="text-xs font-semibold px-2 py-1 rounded-lg border border-slate-200 bg-white text-slate-700 cursor-pointer focus:outline-none"
              >
                <option value="all">Tất cả mật độ</option>
                <option value="low">Chỉ xem: Vắng</option>
                <option value="medium">Chỉ xem: Bình thường</option>
                <option value="high">Chỉ xem: Đông đúc</option>
              </select>
            </div>

            <input
              type="text"
              placeholder="Tìm kiếm điểm tham quan..."
              value={searchQuery}
              onChange={(e) => setSearchQuery(e.target.value)}
              className="w-full text-xs px-3 py-1.5 rounded-xl border border-slate-200 bg-white focus:outline-none focus:border-blue-600 transition"
            />
          </div>

          {/* Vùng danh sách POI cuộn độc lập */}
          <div className="flex-1 overflow-y-auto p-3 space-y-2">
            {filteredAttractions.length === 0 ? (
              <div className="text-center py-10 text-slate-400 text-xs font-medium">
                Không tìm thấy điểm tham quan phù hợp
              </div>
            ) : (
              filteredAttractions.map((a) => {
                const domain = DOMAIN_CONFIG[a.category] ?? DOMAIN_CONFIG.attraction;
                const info = CROWD_COLORS[a.crowd_level] ?? CROWD_COLORS.unknown;
                const status = STATUS_TEXT[a.operating_status] ?? STATUS_TEXT.unknown;
                const isSelected = selectedId === a.service_id;

                return (
                  <div
                    key={a.service_id}
                    id={`poi-card-${a.service_id}`}
                    onClick={() => selectPoi(a, true)}
                    className={`p-3 rounded-xl border transition-all cursor-pointer text-xs ${
                      isSelected
                        ? "bg-blue-50/90 border-blue-500 shadow-xs ring-1 ring-blue-500"
                        : "bg-white hover:bg-slate-50 border-slate-200/80 hover:border-slate-300"
                    }`}
                  >
                    <div className="flex items-start justify-between gap-2">
                      <div>
                        <div className="flex items-center gap-1.5 mb-1">
                          <span
                            className="w-2 h-2 rounded-full inline-block"
                            style={{ backgroundColor: domain.color }}
                          />
                          <span className="text-[10px] font-bold text-slate-500">
                            {domain.label}
                          </span>
                        </div>
                        <p className="font-bold text-slate-900 leading-snug">{a.name}</p>
                      </div>

                      <span className={`text-[10px] font-bold px-1.5 py-0.5 rounded border shrink-0 ${info.bg} ${info.text} ${info.border}`}>
                        {info.label}
                      </span>
                    </div>

                    <div className="mt-2 flex items-center justify-between text-[11px] text-slate-500 font-medium">
                      <span className={status.text}>{status.label}</span>
                      {a.current_people !== null && a.capacity && (
                        <span>
                          {a.current_people}/{a.capacity} khách
                        </span>
                      )}
                      {a.wait_minutes !== null && (
                        <span className="font-mono font-bold text-teal-800">
                          Chờ {a.wait_minutes}p
                        </span>
                      )}
                    </div>
                  </div>
                );
              })
            )}
          </div>
        </div>
      </div>
    </div>
  );
}
