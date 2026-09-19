"use client";

import React, { useEffect, useRef, useState } from "react";

export interface PlanStop {
  name: string;
  lat: number;
  lng: number;
  time?: string;
  duration_minutes?: number;
  note?: string;
}

interface StepInstruction {
  instruction: string;
  distance: number;
  duration: number;
  type?: string;
  modifier?: string;
  name?: string;
  location?: [number, number]; // [lng, lat]
}

interface RouteLeg {
  id: string;
  distance: number;
  duration: number;
  summary: string;
  fromName: string;
  toName: string;
  modeLabel: string;
  steps: StepInstruction[];
}

interface ChatMapboxMessageProps {
  stops: PlanStop[];
  travelMode?: string;
  planId: string;
  dayLabel?: string;
}

const CAR_ROUTE_COLOR = "#2563eb"; // Xanh dương cho tuyến lái xe ô tô từ vị trí hiện tại
const PARK_ROUTE_COLOR = "#0f766e"; // Xanh ngọc cho tuyến giữa các điểm đến
const STOP_MARKER_BG = "#0f766e";

// Tọa độ Ga Cáp Treo VinWonders trên đất liền (Cảng Cầu Đá / An Viên Nha Trang)
const VINWONDERS_MAINLAND_GATE: [number, number] = [109.2178, 12.2023]; // [lng, lat]

function mapboxProfile(mode: string): string {
  if (mode === "walking") return "walking";
  if (mode === "cycling") return "cycling";
  return "driving";
}

function formatDistance(meters: number): string {
  if (!meters || isNaN(meters)) return "0 m";
  if (meters < 1000) return `${Math.round(meters)} m`;
  return `${(meters / 1000).toFixed(1)} km`;
}

function formatDuration(seconds: number): string {
  if (!seconds || isNaN(seconds)) return "0 phút";
  const mins = Math.round(seconds / 60);
  if (mins < 60) return `${mins} phút`;
  const hours = Math.floor(mins / 60);
  const remMins = mins % 60;
  return remMins > 0 ? `${hours} giờ ${remMins} phút` : `${hours} giờ`;
}

function getManeuverSvgString(type?: string, modifier?: string, className: string = "w-4 h-4"): string {
  if (type === "arrive") {
    return `<svg class="${className}" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.2"><circle cx="12" cy="12" r="8"></circle><circle cx="12" cy="12" r="3" fill="currentColor"></circle></svg>`;
  }
  if (type === "roundabout" || type === "rotary") {
    return `<svg class="${className}" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.2" stroke-linecap="round" stroke-linejoin="round"><path d="M21 12a9 9 0 1 1-6.219-8.56"></path><polyline points="15 2 15 8 9 8"></polyline></svg>`;
  }
  if (modifier?.includes("uturn")) {
    return `<svg class="${className}" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.2" stroke-linecap="round" stroke-linejoin="round"><path d="M9 10v7a2 2 0 0 0 2 2h0a2 2 0 0 0 2-2V7a4 4 0 0 0-8 0v2"></path><polyline points="2 7 5 10 8 7"></polyline></svg>`;
  }
  if (modifier?.includes("sharp left")) {
    return `<svg class="${className}" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.2" stroke-linecap="round" stroke-linejoin="round"><path d="M19 20v-7a4 4 0 0 0-4-4H5"></path><polyline points="9 5 5 9 9 13"></polyline></svg>`;
  }
  if (modifier?.includes("sharp right")) {
    return `<svg class="${className}" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.2" stroke-linecap="round" stroke-linejoin="round"><path d="M5 20v-7a4 4 0 0 1 4-4h10"></path><polyline points="15 5 19 9 15 13"></polyline></svg>`;
  }
  if (modifier?.includes("slight left")) {
    return `<svg class="${className}" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.2" stroke-linecap="round" stroke-linejoin="round"><path d="M17 21l-5-10L7 5"></path><polyline points="7 11 7 5 13 5"></polyline></svg>`;
  }
  if (modifier?.includes("slight right")) {
    return `<svg class="${className}" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.2" stroke-linecap="round" stroke-linejoin="round"><path d="M7 21l5-10L17 5"></path><polyline points="11 5 17 5 17 11"></polyline></svg>`;
  }
  if (modifier?.includes("left")) {
    return `<svg class="${className}" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.2" stroke-linecap="round" stroke-linejoin="round"><path d="M18 19v-6a4 4 0 0 0-4-4H6"></path><polyline points="10 5 6 9 10 13"></polyline></svg>`;
  }
  if (modifier?.includes("right")) {
    return `<svg class="${className}" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.2" stroke-linecap="round" stroke-linejoin="round"><path d="M6 19v-6a4 4 0 0 1 4-4h8"></path><polyline points="14 5 18 9 14 13"></polyline></svg>`;
  }
  return `<svg class="${className}" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.2" stroke-linecap="round" stroke-linejoin="round"><line x1="12" y1="19" x2="12" y2="5"></line><polyline points="6 11 12 5 18 11"></polyline></svg>`;
}

function ManeuverIcon({
  type,
  modifier,
  className = "w-4 h-4",
}: {
  type?: string;
  modifier?: string;
  className?: string;
}) {
  return (
    <span
      className="inline-flex items-center justify-center shrink-0"
      dangerouslySetInnerHTML={{ __html: getManeuverSvgString(type, modifier, className) }}
    />
  );
}

// Bảng sửa tọa độ chuẩn các danh thắng Nha Trang tránh bị rơi ra biển
const NHA_TRANG_KNOWN_COORDS: Record<string, [number, number]> = {
  "tháp bà": [109.1958, 12.2655],
  "ponagar": [109.1958, 12.2655],
  "chợ đầm": [109.1915, 12.2536],
  "nhà thờ núi": [109.1894, 12.2471],
  "nhà thờ đá": [109.1894, 12.2471],
  "bãi biển trần phú": [109.1972, 12.2388],
  "trần phú": [109.1972, 12.2388],
  "chùa long sơn": [109.1804, 12.2505],
  "viện hải dương học": [109.2005, 12.2078],
  "hải dương học": [109.2005, 12.2078],
  "quán ăn hải sản bờ kè": [109.1965, 12.2605],
  "hải sản bờ kè": [109.1965, 12.2605],
  "hòn chồng": [109.2062, 12.2718],
  "tắm bùn i-resort": [109.1762, 12.2815],
  "i-resort": [109.1762, 12.2815],
  "suối khoáng nóng tháp bà": [109.1852, 12.2762],
};

function sanitizeCoordinate(stop: PlanStop): [number, number] {
  const nameLower = stop.name.toLowerCase();
  for (const [key, coords] of Object.entries(NHA_TRANG_KNOWN_COORDS)) {
    if (nameLower.includes(key)) {
      return coords;
    }
  }

  const isIsland = nameLower.includes("vinpearl") || nameLower.includes("vinwonders") || nameLower.includes("hòn tre");
  if (!isIsland && stop.lng > 109.208 && stop.lat >= 12.20 && stop.lat <= 12.27) {
    return [Math.min(stop.lng, 109.1975), stop.lat];
  }

  return [stop.lng, stop.lat];
}

export default function ChatMapboxMessage({
  stops,
  travelMode = "driving",
  planId,
  dayLabel,
}: ChatMapboxMessageProps) {
  const inlineContainerRef = useRef<HTMLDivElement>(null);
  const modalContainerRef = useRef<HTMLDivElement>(null);

  const inlineMapRef = useRef<any>(null);
  const modalMapRef = useRef<any>(null);
  const navMarkerRef = useRef<any>(null);

  const [isModalOpen, setIsModalOpen] = useState(false);
  const userLocationRef = useRef<{ lat: number; lng: number }>({ lat: 21.0285, lng: 105.8542 });
  const [userLocation, setUserLocation] = useState<{ lat: number; lng: number } | null>(null);

  const [allRouteLegs, setAllRouteLegs] = useState<RouteLeg[]>([]);
  const [allNavSteps, setAllNavSteps] = useState<StepInstruction[]>([]);
  const [currentStepIdx, setCurrentStepIdx] = useState<number>(0);
  const [totalTripDistance, setTotalTripDistance] = useState<number>(0);
  const [totalTripDuration, setTotalTripDuration] = useState<number>(0);

  const sanitizedStops = stops
    .filter((s) => typeof s.lat === "number" && typeof s.lng === "number" && !isNaN(s.lat) && !isNaN(s.lng))
    .map((s) => {
      const [lng, lat] = sanitizeCoordinate(s);
      return { ...s, lat, lng };
    });

  // Xác định Điểm 1 có ở trên đảo không để ô tô đi tới cảng đất liền
  const isStop1OnIsland = sanitizedStops.length > 0 && (
    sanitizedStops[0].lng > 109.23 ||
    sanitizedStops[0].name.toLowerCase().includes("vinwonders") ||
    sanitizedStops[0].name.toLowerCase().includes("vinpearl") ||
    sanitizedStops[0].name.toLowerCase().includes("hòn tre")
  );

  const carDestinationCoord: [number, number] = isStop1OnIsland
    ? VINWONDERS_MAINLAND_GATE
    : [sanitizedStops[0]?.lng || 109.1958, sanitizedStops[0]?.lat || 12.2655];

  const carDestinationName = isStop1OnIsland
    ? "Ga Cáp Treo VinWonders (Bến Cầu Đá Nha Trang)"
    : (sanitizedStops[0]?.name || "Điểm 1");

  // Profile di chuyển nội bộ công viên hoặc thành phố
  const parkProfile = isStop1OnIsland ? "walking" : mapboxProfile(travelMode);

  // 1. Khởi tạo Inline Preview Map
  useEffect(() => {
    if (typeof window === "undefined") return;
    if (!inlineContainerRef.current) return;
    if (sanitizedStops.length === 0) return;

    const token = process.env.NEXT_PUBLIC_MAPBOX_TOKEN;
    if (!token) return;

    let cancelled = false;

    async function initInlineMap() {
      const mapboxgl = (await import("mapbox-gl")).default;
      if (cancelled || !inlineContainerRef.current) return;

      if (inlineMapRef.current) {
        try {
          inlineMapRef.current.remove();
        } catch (_) {}
        inlineMapRef.current = null;
      }

      mapboxgl.accessToken = token!;

      const map = new mapboxgl.Map({
        container: inlineContainerRef.current!,
        style: "mapbox://styles/mapbox/streets-v12",
        center: [sanitizedStops[0].lng, sanitizedStops[0].lat],
        zoom: 13,
        attributionControl: false,
        scrollZoom: false,
        interactive: false,
        accessToken: token!,
      } as any);

      inlineMapRef.current = map;

      map.on("load", async () => {
        if (cancelled) return;

        sanitizedStops.forEach((stop, idx) => {
          const el = document.createElement("div");
          el.style.cssText = [
            "width: 22px",
            "height: 22px",
            `background-color: ${STOP_MARKER_BG}`,
            "color: #ffffff",
            "border: 2px solid #ffffff",
            "border-radius: 50%",
            "display: flex",
            "align-items: center",
            "justify-content: center",
            "font-size: 11px",
            "font-weight: 700",
            "box-shadow: 0 2px 6px rgba(0,0,0,0.3)",
          ].join(";");
          el.textContent = String(idx + 1);

          new mapboxgl.Marker({ element: el })
            .setLngLat([stop.lng, stop.lat])
            .addTo(map);
        });

        // Tuyến đường nội bộ giữa các điểm dừng
        if (sanitizedStops.length >= 2) {
          const coords = sanitizedStops.map((s) => `${s.lng},${s.lat}`).join(";");
          const url = `https://api.mapbox.com/directions/v5/mapbox/${parkProfile}/${coords}?geometries=geojson&overview=simplified&access_token=${token}`;
          try {
            const res = await fetch(url);
            if (res.ok) {
              const data = await res.json();
              const route = data?.routes?.[0]?.geometry;
              if (route && !cancelled && map.isStyleLoaded()) {
                map.addSource(`inline-route-${planId}`, {
                  type: "geojson",
                  data: { type: "Feature", properties: {}, geometry: route },
                });
                map.addLayer({
                  id: `inline-line-${planId}`,
                  type: "line",
                  source: `inline-route-${planId}`,
                  layout: { "line-join": "round", "line-cap": "round" },
                  paint: { "line-color": PARK_ROUTE_COLOR, "line-width": 3.5, "line-opacity": 0.9 },
                });
              }
            }
          } catch (_) {}
        }

        const bounds = sanitizedStops.reduce(
          (b, s) => b.extend([s.lng, s.lat] as [number, number]),
          new mapboxgl.LngLatBounds([sanitizedStops[0].lng, sanitizedStops[0].lat], [sanitizedStops[0].lng, sanitizedStops[0].lat])
        );
        map.fitBounds(bounds, { padding: 35, maxZoom: 15, duration: 0 });
      });
    }

    initInlineMap();

    return () => {
      cancelled = true;
      if (inlineMapRef.current) {
        try {
          inlineMapRef.current.remove();
        } catch (_) {}
        inlineMapRef.current = null;
      }
    };
  }, [planId]);

  // 2. Khởi tạo Modal Map: VẼ ĐẦY ĐỦ TUYẾN Ô TÔ TỪ VỊ TRÍ HIỆN TẠI ĐẾN ĐIỂM 1 VÀ TỪ ĐIỂM 1 -> 2
  useEffect(() => {
    if (!isModalOpen) return;

    const token = process.env.NEXT_PUBLIC_MAPBOX_TOKEN;
    if (!token) return;

    let cancelled = false;
    let resizeObserver: ResizeObserver | null = null;

    async function initModalMap() {
      // 1. Lấy vị trí người dùng an toàn một lần duy nhất, không kích hoạt re-render loop
      let currentUser = userLocationRef.current;
      if (typeof navigator !== "undefined" && navigator.geolocation && currentUser.lat === 21.0285) {
        try {
          const pos = await new Promise<GeolocationPosition>((resolve, reject) => {
            navigator.geolocation.getCurrentPosition(resolve, reject, { timeout: 2000, maximumAge: 60000 });
          });
          if (!cancelled && pos?.coords) {
            currentUser = { lat: pos.coords.latitude, lng: pos.coords.longitude };
            userLocationRef.current = currentUser;
            setUserLocation(currentUser);
          }
        } catch (_) {}
      }

      const mapboxgl = (await import("mapbox-gl")).default;
      if (cancelled || !modalContainerRef.current) return;

      if (modalMapRef.current) {
        try {
          modalMapRef.current.remove();
        } catch (_) {}
        modalMapRef.current = null;
      }

      mapboxgl.accessToken = token!;

      const map = new mapboxgl.Map({
        container: modalContainerRef.current!,
        style: "mapbox://styles/mapbox/streets-v12",
        center: [sanitizedStops[0]?.lng || 109.1958, sanitizedStops[0]?.lat || 12.2655],
        zoom: 6,
        attributionControl: false,
        accessToken: token!,
      } as any);

      map.addControl(new mapboxgl.NavigationControl({ showCompass: true }), "top-right");
      modalMapRef.current = map;

      // Đảm bảo canvas WebGL luôn chiếm trọn 100% diện tích modal, không bao giờ bị xám hay cắt xén
      if (typeof ResizeObserver !== "undefined" && modalContainerRef.current) {
        resizeObserver = new ResizeObserver(() => {
          if (!cancelled && modalMapRef.current) {
            modalMapRef.current.resize();
          }
        });
        resizeObserver.observe(modalContainerRef.current);
      }

      map.on("load", async () => {
        if (cancelled) return;
        map.resize();
        setTimeout(() => { if (!cancelled && modalMapRef.current) modalMapRef.current.resize(); }, 150);
        setTimeout(() => { if (!cancelled && modalMapRef.current) modalMapRef.current.resize(); }, 400);

        const collectedLegs: RouteLeg[] = [];
        const collectedSteps: StepInstruction[] = [];
        let totalMeters = 0;
        let totalSecs = 0;

        // 1. CẮM MARKER VỊ TRÍ HIỆN TẠI CỦA BẠN
        const userEl = document.createElement("div");
        userEl.style.cssText = "position: relative; width: 24px; height: 24px;";
        userEl.innerHTML = `
          <div style="position: absolute; width: 100%; height: 100%; border-radius: 50%; background: rgba(37, 99, 235, 0.35); animation: ping 1.8s cubic-bezier(0, 0, 0.2, 1) infinite;"></div>
          <div style="position: relative; width: 20px; height: 20px; border-radius: 50%; background: #2563eb; border: 3px solid #ffffff; box-shadow: 0 2px 8px rgba(0,0,0,0.35); margin: 2px;"></div>
        `;
        const userPopup = new mapboxgl.Popup({ offset: 14 }).setHTML(
          '<div style="font-size: 12px; font-weight: 700; color: #1e40af; padding: 2px 4px;">Vị trí hiện tại của bạn</div>'
        );
        new mapboxgl.Marker({ element: userEl })
          .setLngLat([currentUser.lng, currentUser.lat])
          .setPopup(userPopup)
          .addTo(map);

        // 2. CẮM MARKERS ĐIỂM DỪNG 1..N
        sanitizedStops.forEach((stop, idx) => {
          const el = document.createElement("div");
          el.className = "cursor-pointer transition-transform hover:scale-110";
          el.style.cssText = [
            "width: 32px",
            "height: 32px",
            `background-color: ${STOP_MARKER_BG}`,
            "color: #ffffff",
            "border: 2.5px solid #ffffff",
            "border-radius: 50%",
            "display: flex",
            "align-items: center",
            "justify-content: center",
            "font-size: 14px",
            "font-weight: 800",
            "box-shadow: 0 3px 10px rgba(0,0,0,0.35)",
          ].join(";");
          el.textContent = String(idx + 1);

          const popupContent = [
            '<div style="font-family: inherit; font-size: 12px; min-width: 170px; padding: 4px;">',
            `<div style="font-weight: 700; color: #0f172a; margin-bottom: 3px; font-size: 13px;">${idx + 1}. ${stop.name}</div>`,
            stop.time ? `<div style="font-size: 11px; color: #0f766e; font-weight: 600;">Dự kiến: ${stop.time}${stop.duration_minutes ? ` (${stop.duration_minutes} phút)` : ""}</div>` : "",
            stop.note ? `<div style="font-size: 11px; color: #475569; margin-top: 3px; line-height: 1.4;">${stop.note}</div>` : "",
            "</div>",
          ].join("");

          const popup = new mapboxgl.Popup({ offset: 18, closeButton: false, maxWidth: "240px" }).setHTML(popupContent);

          new mapboxgl.Marker({ element: el })
            .setLngLat([stop.lng, stop.lat])
            .setPopup(popup)
            .addTo(map);
        });

        // 3. VẼ TUYẾN Ô TÔ ĐI ĐƯỢC TỪ VỊ TRÍ HIỆN TẠI ĐẾN ĐIỂM 1
        const carRouteUrl = `https://api.mapbox.com/directions/v5/mapbox/driving/${currentUser.lng},${currentUser.lat};${carDestinationCoord[0]},${carDestinationCoord[1]}?geometries=geojson&overview=full&steps=true&language=vi&access_token=${token}`;

        try {
          const carRes = await fetch(carRouteUrl);
          if (carRes.ok) {
            const carData = await carRes.json();
            const carRoute = carData?.routes?.[0];
            if (carRoute && map.isStyleLoaded()) {
              totalMeters += carRoute.distance || 0;
              totalSecs += carRoute.duration || 0;

              const carSteps: StepInstruction[] = (carRoute.legs?.[0]?.steps || []).map((st: any) => ({
                instruction: st.maneuver?.instruction || "",
                distance: st.distance || 0,
                duration: st.duration || 0,
                type: st.maneuver?.type,
                modifier: st.maneuver?.modifier,
                name: st.name,
                location: st.maneuver?.location,
              }));

              collectedLegs.push({
                id: "leg-car-from-user",
                distance: carRoute.distance,
                duration: carRoute.duration,
                summary: "Tuyến đường lái xe ô tô",
                fromName: "Vị trí hiện tại của bạn",
                toName: carDestinationName,
                modeLabel: "Lái xe ô tô",
                steps: carSteps,
              });

              collectedSteps.push(...carSteps);

              // Vẽ tuyến lái xe ô tô
              map.addSource("car-route-src", {
                type: "geojson",
                data: { type: "Feature", properties: {}, geometry: carRoute.geometry },
              });

              map.addLayer({
                id: "car-route-casing",
                type: "line",
                source: "car-route-src",
                layout: { "line-join": "round", "line-cap": "round" },
                paint: { "line-color": "#ffffff", "line-width": 8, "line-opacity": 0.9 },
              });

              map.addLayer({
                id: "car-route-line",
                type: "line",
                source: "car-route-src",
                layout: { "line-join": "round", "line-cap": "round" },
                paint: { "line-color": CAR_ROUTE_COLOR, "line-width": 5.5, "line-opacity": 0.95 },
              });
            }
          }
        } catch (err) {
          console.warn("Lỗi tính tuyến ô tô từ vị trí người dùng:", err);
        }

        // 4. VẼ TUYẾN ĐƯỜNG NỐI TỪ ĐIỂM 1 -> ĐIỂM 2 -> ĐIỂM 3
        if (sanitizedStops.length >= 2) {
          const parkCoords = sanitizedStops.map((s) => `${s.lng},${s.lat}`).join(";");
          const parkRouteUrl = `https://api.mapbox.com/directions/v5/mapbox/${parkProfile}/${parkCoords}?geometries=geojson&overview=full&steps=true&language=vi&access_token=${token}`;

          try {
            const parkRes = await fetch(parkRouteUrl);
            if (parkRes.ok) {
              const parkData = await parkRes.json();
              const parkRoute = parkData?.routes?.[0];
              if (parkRoute && map.isStyleLoaded()) {
                totalMeters += parkRoute.distance || 0;
                totalSecs += parkRoute.duration || 0;

                const legs = parkRoute.legs || [];
                legs.forEach((leg: any, i: number) => {
                  const legSteps: StepInstruction[] = (leg.steps || []).map((st: any) => ({
                    instruction: st.maneuver?.instruction || "",
                    distance: st.distance || 0,
                    duration: st.duration || 0,
                    type: st.maneuver?.type,
                    modifier: st.maneuver?.modifier,
                    name: st.name,
                    location: st.maneuver?.location,
                  }));

                  collectedLegs.push({
                    id: `leg-park-${i}`,
                    distance: leg.distance,
                    duration: leg.duration,
                    summary: `Chặng ${i + 1}`,
                    fromName: sanitizedStops[i]?.name || `Điểm ${i + 1}`,
                    toName: sanitizedStops[i + 1]?.name || `Điểm ${i + 2}`,
                    modeLabel: isStop1OnIsland ? "Đi bộ tham quan" : "Di chuyển tham quan",
                    steps: legSteps,
                  });

                  collectedSteps.push(...legSteps);
                });

                // Vẽ tuyến tham quan giữa các điểm 1 -> 2 -> 3
                map.addSource("park-route-src", {
                  type: "geojson",
                  data: { type: "Feature", properties: {}, geometry: parkRoute.geometry },
                });

                map.addLayer({
                  id: "park-route-casing",
                  type: "line",
                  source: "park-route-src",
                  layout: { "line-join": "round", "line-cap": "round" },
                  paint: { "line-color": "#ffffff", "line-width": 8, "line-opacity": 0.9 },
                });

                map.addLayer({
                  id: "park-route-line",
                  type: "line",
                  source: "park-route-src",
                  layout: { "line-join": "round", "line-cap": "round" },
                  paint: { "line-color": PARK_ROUTE_COLOR, "line-width": 5.5, "line-opacity": 0.95 },
                });
              }
            }
          } catch (err) {
            console.warn("Lỗi tính tuyến đường giữa các điểm:", err);
          }
        }

        setAllRouteLegs(collectedLegs);
        setAllNavSteps(collectedSteps);
        setTotalTripDistance(totalMeters);
        setTotalTripDuration(totalSecs);

        // MẶC ĐỊNH FITBOUNDS BAO GỒM TOÀN BỘ TUYẾN ĐƯỜNG TỪ VỊ TRÍ BẠN ĐẾN TẤT CẢ CÁC ĐIỂM
        const allBounds = new mapboxgl.LngLatBounds([currentUser.lng, currentUser.lat], [currentUser.lng, currentUser.lat]);
        sanitizedStops.forEach((s) => allBounds.extend([s.lng, s.lat]));
        map.fitBounds(allBounds, { padding: 60, duration: 1000 });
      });
    }

    initModalMap();

    return () => {
      cancelled = true;
      if (resizeObserver) {
        resizeObserver.disconnect();
        resizeObserver = null;
      }
      if (modalMapRef.current) {
        try {
          modalMapRef.current.remove();
        } catch (_) {}
        modalMapRef.current = null;
      }
    };
  }, [isModalOpen, planId]);

  // Phóng to khu vực Nha Trang (Điểm 1 -> 2 -> ...)
  const zoomToDestinationArea = () => {
    if (!modalMapRef.current || sanitizedStops.length === 0) return;
    import("mapbox-gl").then(({ default: mapboxgl }) => {
      const bounds = sanitizedStops.reduce(
        (b, s) => b.extend([s.lng, s.lat] as [number, number]),
        new mapboxgl.LngLatBounds([sanitizedStops[0].lng, sanitizedStops[0].lat], [sanitizedStops[0].lng, sanitizedStops[0].lat])
      );
      modalMapRef.current.fitBounds(bounds, { padding: 80, maxZoom: 16, duration: 1000 });
    });
  };

  // Phóng to toàn bộ hành trình (từ vị trí của bạn đến điểm cuối)
  const zoomToFullTrip = () => {
    if (!modalMapRef.current || sanitizedStops.length === 0) return;
    const currentUser = userLocationRef.current || { lat: 21.0285, lng: 105.8542 };
    import("mapbox-gl").then(({ default: mapboxgl }) => {
      const allBounds = new mapboxgl.LngLatBounds([currentUser.lng, currentUser.lat], [currentUser.lng, currentUser.lat]);
      sanitizedStops.forEach((s) => allBounds.extend([s.lng, s.lat]));
      modalMapRef.current.fitBounds(allBounds, { padding: 60, duration: 1000 });
    });
  };

  // Nhảy đến một bước chỉ đường trên bản đồ (Navigation FlyTo Step)
  const jumpToStep = (idx: number) => {
    if (!allNavSteps[idx] || !modalMapRef.current) return;
    setCurrentStepIdx(idx);

    const step = allNavSteps[idx];
    if (step.location) {
      import("mapbox-gl").then(({ default: mapboxgl }) => {
        const map = modalMapRef.current;
        map.flyTo({
          center: step.location,
          zoom: 16.5,
          pitch: 35,
          duration: 1000,
        });

        if (navMarkerRef.current) {
          navMarkerRef.current.remove();
        }
        const navEl = document.createElement("div");
        navEl.style.cssText = [
          "width: 30px",
          "height: 30px",
          "background: #2563eb",
          "color: #ffffff",
          "border: 2px solid #ffffff",
          "border-radius: 50%",
          "display: flex",
          "align-items: center",
          "justify-content: center",
          "box-shadow: 0 4px 12px rgba(0,0,0,0.4)",
        ].join(";");
        navEl.innerHTML = getManeuverSvgString(step.type, step.modifier, "w-4 h-4 text-white");

        navMarkerRef.current = new mapboxgl.Marker({ element: navEl })
          .setLngLat(step.location!)
          .addTo(map);
      });
    }
  };

  // Mở Google Maps
  const handleOpenGoogleMaps = () => {
    if (sanitizedStops.length === 0) return;

    const lastStop = sanitizedStops[sanitizedStops.length - 1];
    const destinationParam = `${lastStop.lat},${lastStop.lng}`;
    let originParam = "";
    let waypointsParam = "";

    const loc = userLocationRef.current;
    if (loc) {
      originParam = `${loc.lat},${loc.lng}`;
      if (sanitizedStops.length > 1) {
        const intermediate = sanitizedStops.slice(0, sanitizedStops.length - 1);
        waypointsParam = intermediate.map((s) => `${s.lat},${s.lng}`).join("|");
      }
    } else {
      originParam = `${sanitizedStops[0].lat},${sanitizedStops[0].lng}`;
      if (sanitizedStops.length > 2) {
        const intermediate = sanitizedStops.slice(1, sanitizedStops.length - 1);
        waypointsParam = intermediate.map((s) => `${s.lat},${s.lng}`).join("|");
      }
    }

    let gmapsUrl = `https://www.google.com/maps/dir/?api=1&origin=${encodeURIComponent(originParam)}&destination=${encodeURIComponent(destinationParam)}&travelmode=driving`;
    if (waypointsParam) {
      gmapsUrl += `&waypoints=${encodeURIComponent(waypointsParam)}`;
    }

    window.open(gmapsUrl, "_blank", "noopener,noreferrer");
  };

  if (sanitizedStops.length === 0) return null;

  const currentNavStep = allNavSteps[currentStepIdx];

  return (
    <>
      {/* 1. GIAO DIỆN INLINE TINH TẾ (Trong khung Chat) */}
      <div
        onClick={() => setIsModalOpen(true)}
        className="group relative my-2.5 w-full cursor-pointer overflow-hidden rounded-xl border border-slate-200 bg-white transition-all hover:border-teal-700 hover:shadow-md"
      >
        <div className="flex items-center justify-between px-3.5 py-2 border-b border-slate-100 bg-slate-50/70 text-xs text-slate-700">
          <span className="font-semibold text-slate-900 tracking-tight">
            {dayLabel ? `${dayLabel} — ` : ""}
            Lộ trình tham quan ({sanitizedStops.length} điểm đến)
          </span>
          <span className="inline-flex items-center gap-1 font-medium text-[11px] text-teal-800 group-hover:underline">
            <span>Xem bản đồ chi tiết</span>
            <svg className="w-3.5 h-3.5 transition-transform group-hover:translate-x-0.5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M10 6H6a2 2 0 00-2 2v10a2 2 0 002 2h10a2 2 0 002-2v-4M14 4h6m0 0v6m0-6L10 14" />
            </svg>
          </span>
        </div>

        <div className="relative">
          <div ref={inlineContainerRef} style={{ width: "100%", height: "210px" }} />
          <div className="absolute inset-0 bg-slate-900/0 group-hover:bg-slate-900/5 transition-colors flex items-center justify-center pointer-events-none">
            <span className="opacity-0 group-hover:opacity-100 transition-opacity bg-white/95 text-slate-800 text-[11px] font-semibold px-3 py-1.5 rounded-full shadow-md border border-slate-200">
              Nhấp để mở bản đồ dẫn đường toàn tuyến
            </span>
          </div>
        </div>
      </div>

      {/* 2. MODAL POPUP NAVIGATION LỚN GIỮA MÀN HÌNH */}
      {isModalOpen && (
        <div className="fixed inset-0 z-50 flex items-center justify-center p-3 md:p-6 bg-slate-950/65 backdrop-blur-xs animate-in fade-in duration-200">
          <div className="relative flex flex-col w-full max-w-6xl h-[90vh] bg-white rounded-2xl shadow-2xl overflow-hidden border border-slate-200">
            {/* Modal Header */}
            <div className="flex items-center justify-between px-5 py-3 border-b border-slate-200 bg-white">
              <div>
                <h3 className="text-base font-bold text-slate-900">
                  {dayLabel ? `${dayLabel} — ` : ""}
                  Chỉ Dẫn Lộ Trình Di Chuyển
                </h3>
                <div className="text-xs text-slate-500 mt-0.5">
                  Tuyến ô tô từ vị trí hiện tại → Điểm 1 → Điểm 2
                  {totalTripDistance > 0 && ` • Tổng quãng đường: ${formatDistance(totalTripDistance)}`}
                  {totalTripDuration > 0 && ` • Thời gian dự kiến: ${formatDuration(totalTripDuration)}`}
                </div>
              </div>

              {/* Nút hành động */}
              <div className="flex items-center gap-2">
                <button
                  type="button"
                  onClick={handleOpenGoogleMaps}
                  className="inline-flex items-center gap-1.5 px-3 py-1.5 rounded-lg bg-teal-800 hover:bg-teal-700 text-white text-xs font-semibold shadow-xs transition-colors cursor-pointer"
                >
                  <svg className="w-3.5 h-3.5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M10 6H6a2 2 0 00-2 2v10a2 2 0 002 2h10a2 2 0 002-2v-4M14 4h6m0 0v6m0-6L10 14" />
                  </svg>
                  <span>Mở Google Maps</span>
                </button>

                <button
                  type="button"
                  onClick={() => setIsModalOpen(false)}
                  className="p-1.5 rounded-lg text-slate-400 hover:text-slate-700 hover:bg-slate-100 transition-colors ml-1 cursor-pointer"
                  title="Đóng (Esc)"
                >
                  <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M6 18L18 6M6 6l12 12" />
                  </svg>
                </button>
              </div>
            </div>

            {/* Modal Body: Bản đồ lớn + Sidebar */}
            <div className="flex-1 flex flex-col md:flex-row overflow-hidden">
              {/* Bản đồ lớn (Trái) */}
              <div className="relative flex-1 h-full min-h-[350px]">
                <div ref={modalContainerRef} className="w-full h-full" />

                {/* THANH CHỈ DẪN ĐIỀU HƯỚNG TRỰC TIẾP TRÊN MAP (Turn-by-Turn Banner) */}
                {allNavSteps.length > 0 && currentNavStep && (
                  <div className="absolute top-3 left-3 right-14 md:right-auto md:max-w-md bg-slate-900/90 backdrop-blur-md text-white rounded-2xl shadow-xl p-3 border border-slate-700 animate-in slide-in-from-top-2">
                    <div className="flex items-start gap-3">
                      <div className="flex h-9 w-9 shrink-0 items-center justify-center rounded-xl bg-blue-600 text-white shadow-xs">
                        <ManeuverIcon type={currentNavStep.type} modifier={currentNavStep.modifier} className="w-5 h-5" />
                      </div>
                      <div className="flex-1 min-w-0">
                        <div className="text-xs font-semibold leading-snug">
                          {currentNavStep.instruction}
                        </div>
                        <div className="text-[11px] text-blue-300 font-mono mt-0.5">
                          {currentNavStep.distance > 0 && `Đi tiếp ${formatDistance(currentNavStep.distance)}`}
                          {currentNavStep.name ? ` • ${currentNavStep.name}` : ""}
                        </div>
                      </div>
                    </div>

                    {/* Điều khiển chuyển bước */}
                    <div className="mt-2.5 pt-2 border-t border-slate-700/80 flex items-center justify-between text-[11px]">
                      <span className="text-slate-400 font-mono">
                        Bước {currentStepIdx + 1} / {allNavSteps.length}
                      </span>
                      <div className="flex items-center gap-1.5">
                        <button
                          type="button"
                          disabled={currentStepIdx === 0}
                          onClick={() => jumpToStep(currentStepIdx - 1)}
                          className="inline-flex items-center gap-1 px-2.5 py-1 rounded-lg bg-slate-800 hover:bg-slate-700 disabled:opacity-30 transition cursor-pointer text-xs"
                        >
                          <svg className="w-3 h-3" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M15 19l-7-7 7-7" />
                          </svg>
                          <span>Trước</span>
                        </button>
                        <button
                          type="button"
                          disabled={currentStepIdx >= allNavSteps.length - 1}
                          onClick={() => jumpToStep(currentStepIdx + 1)}
                          className="inline-flex items-center gap-1 px-2.5 py-1 rounded-lg bg-blue-600 hover:bg-blue-500 font-semibold disabled:opacity-30 transition cursor-pointer text-xs"
                        >
                          <span>Tiếp theo</span>
                          <svg className="w-3 h-3" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M9 5l7 7-7 7" />
                          </svg>
                        </button>
                      </div>
                    </div>
                  </div>
                )}

                {/* NÚT CHUYỂN NHANH GÓC NHÌN (QUICK VIEW TOGGLE) */}
                <div className="absolute bottom-3 left-3 bg-white/95 backdrop-blur-xs p-1.5 rounded-xl text-[11px] border border-slate-200 shadow-md flex items-center gap-1.5">
                  <button
                    type="button"
                    onClick={zoomToFullTrip}
                    className="px-2.5 py-1 rounded-lg bg-blue-50 hover:bg-blue-100 text-blue-700 font-semibold border border-blue-200 transition cursor-pointer"
                  >
                    Toàn tuyến từ bạn
                  </button>
                  <button
                    type="button"
                    onClick={zoomToDestinationArea}
                    className="px-2.5 py-1 rounded-lg bg-teal-50 hover:bg-teal-100 text-teal-800 font-semibold border border-teal-200 transition cursor-pointer"
                  >
                    Khu vực Nha Trang
                  </button>
                </div>

                {/* Legend góc phải dưới */}
                <div className="absolute bottom-3 right-3 hidden sm:flex bg-white/95 backdrop-blur-xs px-3 py-1.5 rounded-lg text-[11px] border border-slate-200 shadow-sm items-center gap-3 pointer-events-none">
                  <span className="flex items-center gap-1.5 text-blue-700 font-semibold">
                    <span className="w-2.5 h-2.5 rounded-full bg-blue-600 inline-block"></span> Tuyến lái xe ô tô
                  </span>
                  <span className="flex items-center gap-1.5 text-teal-800 font-semibold">
                    <span className="w-2.5 h-2.5 rounded-full bg-teal-800 inline-block"></span> Tuyến giữa các điểm dừng
                  </span>
                </div>
              </div>

              {/* Sidebar Danh sách Lộ trình & Hướng dẫn (Phải) */}
              <div className="w-full md:w-80 lg:w-96 bg-slate-50/95 border-t md:border-t-0 md:border-l border-slate-200 flex flex-col overflow-hidden">
                <div className="px-4 py-3 border-b border-slate-200 bg-white">
                  <h4 className="text-xs font-bold uppercase tracking-wider text-slate-800">
                    Lộ trình các chặng
                  </h4>
                  <p className="text-[11px] text-slate-500 mt-0.5">
                    Đã vẽ tuyến đường ô tô từ vị trí của bạn đến Điểm 1 và Điểm 2
                  </p>
                </div>

                <div className="flex-1 overflow-y-auto p-3 space-y-3 text-xs">
                  {allRouteLegs.map((leg, legIdx) => (
                    <div key={leg.id || legIdx} className="rounded-xl border border-slate-200 bg-white p-3 shadow-2xs">
                      <div className="font-bold text-slate-900 text-xs mb-1 flex items-center justify-between">
                        <span className={legIdx === 0 ? "text-blue-700" : "text-teal-800"}>
                          {leg.modeLabel}
                        </span>
                        <span className="text-[11px] text-slate-500 font-mono font-normal">
                          {formatDistance(leg.distance)} ({formatDuration(leg.duration)})
                        </span>
                      </div>
                      <div className="text-[11px] text-slate-700 font-medium mb-2">
                        {leg.fromName} → {leg.toName}
                      </div>

                      {/* Các bước rẽ */}
                      <div className={`space-y-1.5 pl-1 border-l-2 ${legIdx === 0 ? "border-blue-600/40" : "border-teal-600/30"}`}>
                        {leg.steps.map((st, sIdx) => {
                          const globalIdx = allRouteLegs.slice(0, legIdx).reduce((acc, l) => acc + l.steps.length, 0) + sIdx;
                          const isActive = currentStepIdx === globalIdx;

                          return (
                            <div
                              key={sIdx}
                              onClick={() => jumpToStep(globalIdx)}
                              className={`flex items-start gap-2 p-1 rounded-lg transition-colors cursor-pointer text-[11px] ${
                                isActive ? (legIdx === 0 ? "bg-blue-50 text-blue-900 font-semibold" : "bg-teal-50 text-teal-900 font-semibold") : "hover:bg-slate-50 text-slate-700"
                              }`}
                            >
                              <div className={legIdx === 0 ? "text-blue-600 shrink-0 w-4 h-4 mt-0.5 flex items-center justify-center" : "text-teal-700 shrink-0 w-4 h-4 mt-0.5 flex items-center justify-center"}>
                                <ManeuverIcon type={st.type} modifier={st.modifier} className="w-3.5 h-3.5" />
                              </div>
                              <div className="flex-1 leading-tight">
                                <div>{st.instruction}</div>
                                {st.distance > 0 && (
                                  <div className="text-[10px] text-slate-400 font-mono mt-0.5">
                                    {formatDistance(st.distance)}
                                  </div>
                                )}
                              </div>
                            </div>
                          );
                        })}
                      </div>
                    </div>
                  ))}
                </div>

                {/* Footer Sidebar */}
                <div className="p-3 border-t border-slate-200 bg-white">
                  <button
                    type="button"
                    onClick={handleOpenGoogleMaps}
                    className="w-full flex items-center justify-center gap-2 py-2.5 px-4 rounded-xl bg-teal-800 hover:bg-teal-700 text-white text-xs font-bold shadow-sm transition-colors cursor-pointer"
                  >
                    <span>Mở dẫn đường bằng Google Maps</span>
                    <svg className="w-3.5 h-3.5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                      <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M14 5l7 7m0 0l-7 7m7-7H3" />
                    </svg>
                  </button>
                </div>
              </div>
            </div>
          </div>
        </div>
      )}
    </>
  );
}
