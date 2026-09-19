"use client";

import React, { useEffect, useRef } from "react";

export interface PlanStop {
  name: string;
  lat: number;
  lng: number;
  time?: string;
  duration_minutes?: number;
  note?: string;
}

interface ChatMapboxMessageProps {
  stops: PlanStop[];
  travelMode?: string;
  planId: string;
  dayLabel?: string;
}

const ROUTE_COLOR = "#2f6f4f";
const MARKER_BG = "#2f6f4f";

function getModeIcon(mode: string): string {
  if (mode === "walking") return "🚶";
  if (mode === "cycling") return "🚲";
  return "🚗";
}

function mapboxProfile(mode: string): string {
  if (mode === "walking") return "walking";
  if (mode === "cycling") return "cycling";
  return "driving";
}

export default function ChatMapboxMessage({
  stops,
  travelMode = "driving",
  planId,
  dayLabel,
}: ChatMapboxMessageProps) {
  const containerRef = useRef<HTMLDivElement>(null);
  const mapRef = useRef<any>(null);

  const validStops = stops.filter(
    (s) =>
      typeof s.lat === "number" &&
      typeof s.lng === "number" &&
      !isNaN(s.lat) &&
      !isNaN(s.lng)
  );

  useEffect(() => {
    if (typeof window === "undefined") return;
    if (!containerRef.current) return;
    if (validStops.length === 0) return;

    const token = process.env.NEXT_PUBLIC_MAPBOX_TOKEN;
    if (!token) {
      console.warn("[ChatMapboxMessage] NEXT_PUBLIC_MAPBOX_TOKEN chưa được cấu hình.");
      return;
    }

    let cancelled = false;

    async function initMap() {
      // Dynamic import để tránh SSR issues với mapbox-gl
      const mapboxgl = (await import("mapbox-gl")).default;

      // Import CSS của Mapbox GL một lần
      if (!document.getElementById("mapbox-gl-css")) {
        const link = document.createElement("link");
        link.id = "mapbox-gl-css";
        link.rel = "stylesheet";
        link.href = "https://api.mapbox.com/mapbox-gl-js/v3.5.1/mapbox-gl.css";
        document.head.appendChild(link);
      }

      if (cancelled || !containerRef.current) return;

      // Hủy instance cũ nếu còn tồn tại (tránh memory leak)
      if (mapRef.current) {
        try {
          mapRef.current.remove();
        } catch (_) {}
        mapRef.current = null;
      }

      mapboxgl.accessToken = token!;

      const map = new mapboxgl.Map({
        container: containerRef.current!,
        style: "mapbox://styles/mapbox/streets-v12",
        center: [validStops[0].lng, validStops[0].lat],
        zoom: 12,
        attributionControl: false,
        scrollZoom: false,
      });

      map.addControl(
        new mapboxgl.AttributionControl({ compact: true }),
        "bottom-right"
      );
      map.addControl(
        new mapboxgl.NavigationControl({ showCompass: false }),
        "top-right"
      );

      mapRef.current = map;

      map.on("load", async () => {
        if (cancelled) return;

        // --- Thêm numbered markers cho từng điểm dừng ---
        validStops.forEach((stop, idx) => {
          const el = document.createElement("div");
          el.style.cssText = [
            "width: 28px",
            "height: 28px",
            `background-color: ${MARKER_BG}`,
            "color: #fff",
            "border: 2.5px solid #fff",
            "border-radius: 50%",
            "display: flex",
            "align-items: center",
            "justify-content: center",
            "font-size: 12px",
            "font-weight: 700",
            "font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif",
            "box-shadow: 0 2px 8px rgba(0,0,0,0.32)",
            "cursor: pointer",
          ].join(";");
          el.textContent = String(idx + 1);

          const popupHtml = [
            '<div style="font-family: -apple-system, BlinkMacSystemFont, \'Segoe UI\', sans-serif; font-size: 12px; min-width: 140px; padding: 2px 0;">',
            `<div style="font-weight: 700; color: #0f172a; margin-bottom: 3px;">${idx + 1}. ${stop.name}</div>`,
            stop.time
              ? `<div style="font-size: 11px; color: ${ROUTE_COLOR}; font-weight: 600; margin-bottom: 2px;">⏰ ${stop.time}${stop.duration_minutes ? ` (${stop.duration_minutes}p)` : ""}</div>`
              : "",
            stop.note
              ? `<div style="font-size: 10px; color: #475569; line-height: 1.4;">${stop.note}</div>`
              : "",
            "</div>",
          ].join("");

          const popup = new mapboxgl.Popup({
            offset: 16,
            closeButton: false,
            maxWidth: "220px",
          }).setHTML(popupHtml);

          new mapboxgl.Marker({ element: el })
            .setLngLat([stop.lng, stop.lat])
            .setPopup(popup)
            .addTo(map);
        });

        // --- Gọi Mapbox Directions API để vẽ route ---
        let routeOk = false;
        if (validStops.length >= 2 && validStops.length <= 25) {
          try {
            const coords = validStops
              .map((s) => `${s.lng},${s.lat}`)
              .join(";");
            const profile = mapboxProfile(travelMode);
            const url =
              `https://api.mapbox.com/directions/v5/mapbox/${profile}/${coords}` +
              `?geometries=geojson&overview=full&access_token=${token}`;

            const res = await fetch(url);
            if (!res.ok) throw new Error(`Directions HTTP ${res.status}`);

            const data = await res.json();
            const route = data?.routes?.[0]?.geometry;

            if (route && !cancelled && map.isStyleLoaded()) {
              const sourceId = `route-src-${planId}`;
              const layerId = `route-line-${planId}`;

              // Xóa layer/source cũ nếu tồn tại (trường hợp re-render)
              if (map.getLayer(layerId)) map.removeLayer(layerId);
              if (map.getSource(sourceId)) map.removeSource(sourceId);

              map.addSource(sourceId, {
                type: "geojson",
                data: {
                  type: "Feature",
                  properties: {},
                  geometry: route,
                },
              });

              map.addLayer({
                id: layerId,
                type: "line",
                source: sourceId,
                layout: {
                  "line-join": "round",
                  "line-cap": "round",
                },
                paint: {
                  "line-color": ROUTE_COLOR,
                  "line-width": 4.5,
                  "line-opacity": 0.9,
                  ...(travelMode === "walking"
                    ? { "line-dasharray": [2, 2] }
                    : {}),
                },
              });

              routeOk = true;
            }
          } catch (err) {
            console.warn("[ChatMapboxMessage] Directions API lỗi:", err);
          }
        }

        // --- fitBounds quanh toàn bộ stops, padding 50px ---
        if (!cancelled && validStops.length > 0) {
          const bounds = validStops.reduce(
            (b, s) => b.extend([s.lng, s.lat] as [number, number]),
            new mapboxgl.LngLatBounds(
              [validStops[0].lng, validStops[0].lat],
              [validStops[0].lng, validStops[0].lat]
            )
          );

          map.fitBounds(bounds, {
            padding: { top: 50, bottom: 50, left: 50, right: 50 },
            maxZoom: 15,
            duration: 800,
          });
        }

        // Đánh dấu route thất bại để hiển thị warning
        if (!routeOk && validStops.length >= 2 && containerRef.current) {
          containerRef.current.setAttribute("data-route-failed", "true");
        }
      });
    }

    initMap().catch((err) => {
      console.error("[ChatMapboxMessage] Lỗi khởi tạo bản đồ:", err);
    });

    // Cleanup: hủy map khi component unmount
    return () => {
      cancelled = true;
      if (mapRef.current) {
        try {
          mapRef.current.remove();
        } catch (_) {}
        mapRef.current = null;
      }
    };
    // planId đảm bảo mỗi plan card render một map instance riêng biệt
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [planId]);

  if (validStops.length === 0) return null;

  return (
    <div className="w-full my-2 rounded-xl overflow-hidden border border-[#e6e3da] bg-[#f4f2eb]/60 shadow-2xs">
      {/* Header bar */}
      <div className="flex items-center justify-between px-3 py-1.5 bg-white border-b border-[#e6e3da] text-[11px] font-semibold text-[#52525b]">
        <span className="flex items-center gap-1.5 text-slate-700">
          <span>{getModeIcon(travelMode)}</span>
          <span>
            {dayLabel ? `${dayLabel} — ` : ""}
            Bản đồ lộ trình ({validStops.length} điểm đến)
          </span>
        </span>
        <span className="text-[10px] font-mono" style={{ color: ROUTE_COLOR }}>
          Mapbox GL
        </span>
      </div>

      {/* Map container — chiều cao cố định 360px, width 100% */}
      <div
        ref={containerRef}
        style={{ width: "100%", height: "360px", position: "relative" }}
      />

      {/* Route failed warning (lazy via MutationObserver) */}
      {validStops.length >= 2 && (
        <RouteFailedWarning containerRef={containerRef} planId={planId} />
      )}
    </div>
  );
}

/**
 * Sub-component nhỏ: watch attribute data-route-failed trên container
 * và hiển thị cảnh báo khi Directions API thất bại.
 */
function RouteFailedWarning({
  containerRef,
  planId,
}: {
  containerRef: React.RefObject<HTMLDivElement | null>;
  planId: string;
}) {
  const [failed, setFailed] = React.useState(false);

  useEffect(() => {
    const el = containerRef.current;
    if (!el) return;

    const check = () => {
      if (el.getAttribute("data-route-failed") === "true") {
        setFailed(true);
      }
    };

    const observer = new MutationObserver(check);
    observer.observe(el, {
      attributes: true,
      attributeFilter: ["data-route-failed"],
    });

    // Kiểm tra ngay lần đầu
    check();

    return () => observer.disconnect();
  }, [containerRef, planId]);

  if (!failed) return null;

  return (
    <div
      className="px-3 py-1.5 border-t border-amber-100 text-[10px] text-center"
      style={{ backgroundColor: "#fffbeb", color: "#92400e" }}
    >
      ⚠️ Không thể tính tuyến đường lúc này.
    </div>
  );
}
