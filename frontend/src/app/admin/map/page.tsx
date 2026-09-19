"use client";
import React, { useEffect, useState, useRef, useCallback } from "react";
import { useAdminAuth } from "../layout";
import { getApiBase } from "../config";

interface NodeData {
  node_id: string;
  name: string;
  x_m: number;
  y_m: number;
  lat?: number;
  lng?: number;
  type: string; // 'hub' | 'poi' | 'junction'
  category?: string;
}

interface GraphData {
  map_id: string;
  canvas_width_m: number;
  canvas_height_m: number;
  nodes: NodeData[];
  edges: {
    edge_id: string;
    from_node_id: string;
    to_node_id: string;
    walking_minutes: number;
    distance_m: number;
    is_open: boolean;
  }[];
  poi_metadata: Record<string, { name: string; zone_id: string; indoor: boolean; category: string }>;
}

interface NavStep {
  instruction: string;
  distance: number;
  duration: number;
  maneuverType: string;
  maneuverModifier?: string;
  location: [number, number]; // [lng, lat]
}

interface RouteDetail {
  mode: "walking" | "driving" | "cycling";
  distanceMeters: number;
  durationMinutes: number;
  isMapboxRoute: boolean;
  steps: NavStep[];
  geometryCoordinates: [number, number][];
}

// Bảng cấu hình Domain / Phân loại theo phong cách Google Maps
export const DOMAIN_CONFIG: Record<
  string,
  {
    label: string;
    iconText: string;
    color: string;
    bgBadge: string;
    borderBadge: string;
    textBadge: string;
    svg: string;
  }
> = {
  hub: {
    label: "Cổng / Trạm chính",
    iconText: "🚩",
    color: "#2563eb", // Royal Blue
    bgBadge: "bg-blue-50",
    borderBadge: "border-blue-200",
    textBadge: "text-blue-700",
    svg: `<svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round"><path d="M4 15s1-1 4-1 5 2 8 2 4-1 4-1V3s-1 1-4 1-5-2-8-2-4 1-4 1z"/><line x1="4" y1="22" x2="4" y2="15"/></svg>`,
  },
  food: {
    label: "Ẩm thực & Cafe",
    iconText: "🍽️",
    color: "#ea580c", // Orange
    bgBadge: "bg-orange-50",
    borderBadge: "border-orange-200",
    textBadge: "text-orange-700",
    svg: `<svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.3" stroke-linecap="round" stroke-linejoin="round"><path d="M18 2v6a3 3 0 0 1-3 3 3 3 0 0 1-3-3V2M15 11v11M5 2v10a2 2 0 0 0 2 2h1a2 2 0 0 0 2-2V2M7 14v8"/></svg>`,
  },
  ride: {
    label: "Trò chơi & Cảm giác mạnh",
    iconText: "🎢",
    color: "#9333ea", // Purple
    bgBadge: "bg-purple-50",
    borderBadge: "border-purple-200",
    textBadge: "text-purple-700",
    svg: `<svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.3" stroke-linecap="round" stroke-linejoin="round"><circle cx="12" cy="12" r="9"/><path d="M12 3v18M3 12h18M5.6 5.6l12.8 12.8M5.6 18.4L18.4 5.6"/></svg>`,
  },
  attraction: {
    label: "Tham quan & Show diễn",
    iconText: "🏰",
    color: "#059669", // Emerald Green
    bgBadge: "bg-emerald-50",
    borderBadge: "border-emerald-200",
    textBadge: "text-emerald-700",
    svg: `<svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.3" stroke-linecap="round" stroke-linejoin="round"><path d="M23 19a2 2 0 0 1-2 2H3a2 2 0 0 1-2-2V8a2 2 0 0 1 2-2h4l2-3h6l2 3h4a2 2 0 0 1 2 2z"/><circle cx="12" cy="13" r="4"/></svg>`,
  },
  shop: {
    label: "Mua sắm & Tiện ích",
    iconText: "🛍️",
    color: "#0284c7", // Sky Blue
    bgBadge: "bg-sky-50",
    borderBadge: "border-sky-200",
    textBadge: "text-sky-700",
    svg: `<svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.3" stroke-linecap="round" stroke-linejoin="round"><path d="M6 2L3 6v14a2 2 0 0 0 2 2h14a2 2 0 0 0 2-2V6l-3-4z"/><line x1="3" y1="6" x2="21" y2="6"/><path d="M16 10a4 4 0 0 1-8 0"/></svg>`,
  },
  hotel: {
    label: "Khách sạn & Resort",
    iconText: "🏨",
    color: "#4f46e5", // Indigo
    bgBadge: "bg-indigo-50",
    borderBadge: "border-indigo-200",
    textBadge: "text-indigo-700",
    svg: `<svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.3" stroke-linecap="round" stroke-linejoin="round"><path d="M2 4v16M2 8h18a2 2 0 0 1 2 2v10M2 17h20M6 8v9"/></svg>`,
  },
  service: {
    label: "Dịch vụ & Di chuyển",
    iconText: "🛥️",
    color: "#0d9488", // Teal
    bgBadge: "bg-teal-50",
    borderBadge: "border-teal-200",
    textBadge: "text-teal-700",
    svg: `<svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.3" stroke-linecap="round" stroke-linejoin="round"><circle cx="12" cy="12" r="10"/><path d="m4.93 4.93 4.24 4.24M14.83 9.17l4.24-4.24M14.83 14.83l4.24 4.24M9.17 14.83l-4.24 4.24"/></svg>`,
  },
};

export default function MapPage() {
  const { token } = useAdminAuth();
  const mapContainerRef = useRef<HTMLDivElement>(null);
  const mapRef = useRef<any>(null);
  const markersRef = useRef<{ [nodeId: string]: { marker: any; element: HTMLElement; category: string } }>({});
  const routeMarkersRef = useRef<any[]>([]);

  const [graph, setGraph] = useState<GraphData | null>(null);
  const [fromNode, setFromNode] = useState("");
  const [toNode, setToNode] = useState("");
  const [travelMode, setTravelMode] = useState<"walking" | "driving" | "cycling">("walking");
  const [filterCategory, setFilterCategory] = useState<string>("all");
  const [routeResult, setRouteResult] = useState<RouteDetail | null>(null);
  const [loading, setLoading] = useState(false);
  const [errorMsg, setErrorMsg] = useState("");
  const [selectedNode, setSelectedNode] = useState<NodeData | null>(null);

  const getEffectiveToken = useCallback(
    () => token || (typeof window !== "undefined" ? localStorage.getItem("admin_token") : null),
    [token]
  );

  // Tải dữ liệu đồ thị các điểm POI từ Backend
  useEffect(() => {
    const curToken = getEffectiveToken();
    const headers: Record<string, string> = curToken ? { Authorization: `Bearer ${curToken}` } : {};
    const apiBase = getApiBase();

    fetch(`${apiBase}/admin/map/graph`, { headers })
      .then((r) => r.json())
      .then((data: GraphData) => {
        setGraph(data);
        const start = data.nodes.find((n) => n.type === "hub")?.node_id ?? data.nodes[0]?.node_id ?? "";
        const destination = data.nodes.find((n) => n.type === "poi" && n.node_id !== start)?.node_id ?? "";
        setFromNode(start);
        setToNode(destination);
      })
      .catch((err) => {
        console.warn("Lỗi tải bản đồ graph:", err);
      });
  }, [getEffectiveToken]);

  // Khởi tạo bản đồ Mapbox GL JS
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

  const nodeMap = graph ? Object.fromEntries(graph.nodes.map((n) => [n.node_id, n])) : {};

  // Lấy danh mục của một node
  const getNodeCategory = useCallback(
    (n: NodeData) => {
      if (n.type === "hub") return "hub";
      if (n.category && DOMAIN_CONFIG[n.category]) return n.category;
      const metaCat = graph?.poi_metadata[n.node_id]?.category;
      if (metaCat && DOMAIN_CONFIG[metaCat]) return metaCat;
      return "attraction";
    },
    [graph]
  );

  // Xóa tuyến đường và marker dẫn đường
  const clearCurrentRoute = () => {
    routeMarkersRef.current.forEach((m) => m.remove());
    routeMarkersRef.current = [];
    if (mapRef.current) {
      const map = mapRef.current;
      if (map.getSource("shortest-path-src")) {
        map.getSource("shortest-path-src").setData({
          type: "Feature",
          properties: {},
          geometry: { type: "LineString", coordinates: [] },
        });
      }
    }
    setRouteResult(null);
  };

  // Tìm đường đi thực tế trên Mapbox (Directions API theo đường đi bộ / xe)
  // Hỗ trợ truyền thẳng startId/destId để gọi tức thì từ nút trong popup mà không bị delay bởi React state
  const handleFindPath = async (overrideFrom?: string, overrideTo?: string) => {
    const startId = overrideFrom || fromNode;
    const destId = overrideTo || toNode;

    if (!startId || !destId || startId === destId) {
      setErrorMsg("Vui lòng chọn 2 điểm khác nhau để tìm đường.");
      return;
    }

    const startNode = nodeMap[startId];
    const destNode = nodeMap[destId];

    if (!startNode?.lng || !startNode?.lat || !destNode?.lng || !destNode?.lat) {
      setErrorMsg("Điểm được chọn chưa có tọa độ GPS hợp lệ.");
      return;
    }

    // Cập nhật lại state form cho đồng bộ
    setFromNode(startId);
    setToNode(destId);
    setLoading(true);
    setErrorMsg("");
    clearCurrentRoute();

    const mbToken = process.env.NEXT_PUBLIC_MAPBOX_TOKEN;
    const map = mapRef.current;

    try {
      let routeCoords: [number, number][] = [];
      let totalDist = 0;
      let totalDurMinutes = 0;
      let steps: NavStep[] = [];
      let isMapbox = false;

      // 1. Gọi Mapbox Directions API để vẽ đường đi thực tế theo các đường nét đứt/lối đi bộ trên map
      if (mbToken) {
        try {
          const profile = travelMode === "driving" ? "driving" : travelMode === "cycling" ? "cycling" : "walking";
          const dirUrl = `https://api.mapbox.com/directions/v5/mapbox/${profile}/${startNode.lng},${startNode.lat};${destNode.lng},${destNode.lat}?geometries=geojson&overview=full&steps=true&language=vi&access_token=${mbToken}`;

          const res = await fetch(dirUrl);
          const data = await res.json();

          if (data.code === "Ok" && data.routes && data.routes.length > 0) {
            const r = data.routes[0];
            routeCoords = r.geometry.coordinates;
            totalDist = Math.round(r.distance);
            totalDurMinutes = Math.max(1, Math.round(r.duration / 60));
            isMapbox = true;

            // Đọc các bước chỉ dẫn turn-by-turn
            if (r.legs && r.legs[0] && r.legs[0].steps) {
              steps = r.legs[0].steps.map((s: any) => ({
                instruction: s.maneuver.instruction,
                distance: Math.round(s.distance),
                duration: Math.round(s.duration),
                maneuverType: s.maneuver.type,
                maneuverModifier: s.maneuver.modifier,
                location: s.maneuver.location,
              }));
            }
          } else {
            console.warn("Mapbox Directions API code:", data.code);
          }
        } catch (dirErr) {
          console.warn("Mapbox Directions API thất bại:", dirErr);
        }
      }

      // 2. Dự phòng: Nếu Mapbox Directions không tìm thấy đường đi bộ cụ thể, dùng đường Dijkstra backend
      if (routeCoords.length === 0) {
        const curToken = getEffectiveToken();
        const headers: Record<string, string> = curToken ? { Authorization: `Bearer ${curToken}` } : {};
        const apiBase = getApiBase();
        const res = await fetch(`${apiBase}/admin/map/path?from_node=${startId}&to_node=${destId}`, { headers });
        if (!res.ok) {
          throw new Error("Không thể tính toán đường đi giữa 2 địa điểm này.");
        }
        const data = await res.json();
        totalDist = data.total_distance_m;
        totalDurMinutes = data.total_walking_minutes;
        data.path_nodes.forEach((nId: string) => {
          const n = nodeMap[nId];
          if (n && n.lng && n.lat) {
            routeCoords.push([n.lng, n.lat]);
          }
        });
        steps = data.path_nodes.map((nId: string, idx: number) => ({
          instruction: `Đi qua điểm ${nodeMap[nId]?.name || nId}`,
          distance: Math.round(totalDist / Math.max(1, data.path_nodes.length - 1)),
          duration: Math.round((totalDurMinutes * 60) / Math.max(1, data.path_nodes.length - 1)),
          maneuverType: idx === 0 ? "depart" : idx === data.path_nodes.length - 1 ? "arrive" : "turn",
          location: [nodeMap[nId]?.lng || 0, nodeMap[nId]?.lat || 0],
        }));
      }

      if (routeCoords.length < 2) {
        throw new Error("Không đủ tọa độ để vẽ đường đi thực tế.");
      }

      // 3. Cập nhật state chi tiết lộ trình
      setRouteResult({
        mode: travelMode,
        distanceMeters: totalDist,
        durationMinutes: totalDurMinutes,
        isMapboxRoute: isMapbox,
        steps: steps,
        geometryCoordinates: routeCoords,
      });

      // 4. Vẽ đường uốn lượn thực tế lên Mapbox
      if (map) {
        const mapboxgl = (await import("mapbox-gl")).default;

        const geojson: any = {
          type: "Feature",
          properties: {},
          geometry: {
            type: "LineString",
            coordinates: routeCoords,
          },
        };

        if (map.getSource("shortest-path-src")) {
          map.getSource("shortest-path-src").setData(geojson);
        } else {
          map.addSource("shortest-path-src", {
            type: "geojson",
            data: geojson,
          });

          // Viền ngoài màu trắng nổi bật
          map.addLayer({
            id: "shortest-path-casing",
            type: "line",
            source: "shortest-path-src",
            layout: { "line-join": "round", "line-cap": "round" },
            paint: { "line-color": "#ffffff", "line-width": 8, "line-opacity": 0.95 },
          });

          // Đường tuyến thực tế màu xanh navy đậm
          map.addLayer({
            id: "shortest-path-line",
            type: "line",
            source: "shortest-path-src",
            layout: { "line-join": "round", "line-cap": "round" },
            paint: { "line-color": "#2563eb", "line-width": 5, "line-opacity": 0.95 },
          });
        }

        // 5. Thêm Marker điểm Xuất phát (Xanh lá) & Điểm đến (Đỏ) nổi bật
        const startEl = document.createElement("div");
        startEl.className = "flex items-center justify-center font-black shadow-lg rounded-full text-white bg-emerald-600 border-2 border-white cursor-pointer";
        startEl.style.width = "28px";
        startEl.style.height = "28px";
        startEl.style.fontSize = "12px";
        startEl.title = `Xuất phát: ${startNode.name}`;
        startEl.innerHTML = `<svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="3" stroke-linecap="round" stroke-linejoin="round"><path d="M5 12h14M12 5l7 7-7 7"/></svg>`;

        const startMarker = new mapboxgl.Marker({ element: startEl, anchor: "center" })
          .setLngLat([startNode.lng, startNode.lat])
          .addTo(map);

        const destEl = document.createElement("div");
        destEl.className = "flex items-center justify-center font-black shadow-lg rounded-full text-white bg-rose-600 border-2 border-white cursor-pointer";
        destEl.style.width = "28px";
        destEl.style.height = "28px";
        destEl.style.fontSize = "12px";
        destEl.title = `Điểm đến: ${destNode.name}`;
        destEl.innerHTML = `<svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round"><path d="M4 15s1-1 4-1 5 2 8 2 4-1 4-1V3s-1 1-4 1-5-2-8-2-4 1-4 1z"></path><line x1="4" y1="22" x2="4" y2="15"></line></svg>`;

        const destMarker = new mapboxgl.Marker({ element: destEl, anchor: "center" })
          .setLngLat([destNode.lng, destNode.lat])
          .addTo(map);

        routeMarkersRef.current = [startMarker, destMarker];

        // 6. Fitbounds bao trọn toàn bộ tuyến đường thực tế
        const bounds = new mapboxgl.LngLatBounds(routeCoords[0], routeCoords[0]);
        routeCoords.forEach((c) => bounds.extend(c));
        map.fitBounds(bounds, { padding: { top: 60, bottom: 60, left: 60, right: 60 }, duration: 800 });
      }
    } catch (err: any) {
      setErrorMsg(err.message || "Lỗi khi tìm đường đi.");
    } finally {
      setLoading(false);
    }
  };

  // Thêm markers POI theo phong cách Google Maps lên bản đồ
  // KHẮC PHỤC TRIỆT ĐỂ LỖI NHÁY (FLICKERING):
  // Root element `el` KHÔNG dùng scale/transition để tránh xung đột với transform: translate của Mapbox.
  // Thay vào đó, scale được bọc hoàn toàn bên trong thẻ `innerWrapper`.
  useEffect(() => {
    if (!mapRef.current || !graph) return;
    const map = mapRef.current;

    import("mapbox-gl").then(({ default: mapboxgl }) => {
      // Xóa markers POI cũ
      Object.values(markersRef.current).forEach((m) => m.marker.remove());
      markersRef.current = {};

      graph.nodes.forEach((node) => {
        if (!node.lat || !node.lng) return;

        const category = getNodeCategory(node);
        const domain = DOMAIN_CONFIG[category] ?? DOMAIN_CONFIG.attraction;
        const isHub = node.type === "hub";

        // 1. Root container (Mapbox định vị bằng transform - TUYỆT ĐỐI KHÔNG SCALE Ở ĐÂY)
        const el = document.createElement("div");
        el.className = "cursor-pointer select-none";
        el.style.pointerEvents = "auto";

        // 2. Inner wrapper: Thực hiện phóng to mượt mà khi hover KHÔNG bị nháy
        const innerWrapper = document.createElement("div");
        innerWrapper.className = "flex flex-col items-center group transition-transform duration-150 ease-out hover:scale-120";
        innerWrapper.style.transformOrigin = "bottom center";

        // 3. Ghim pin Google Maps (hình giọt nước xoay góc -45 độ)
        const pin = document.createElement("div");
        const pinSize = isHub ? 30 : 25;
        pin.style.cssText = `
          width: ${pinSize}px;
          height: ${pinSize}px;
          background-color: ${domain.color};
          color: #ffffff;
          border: 2px solid #ffffff;
          border-radius: 50% 50% 50% 0;
          transform: rotate(-45deg);
          display: flex;
          align-items: center;
          justify-content: center;
          box-shadow: 0 3px 8px rgba(0,0,0,0.35);
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

        // 4. Nhãn tên POI (văn bản viền trắng chống lóa, pointerEvents: none để không bắt chuột)
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
        label.textContent = node.name;

        innerWrapper.appendChild(pin);
        innerWrapper.appendChild(label);
        el.appendChild(innerWrapper);

        // 5. Khởi tạo Popup bằng DOM thật (setDOMContent) để bắt sự kiện click 100% tin cậy
        const popupContainer = document.createElement("div");
        popupContainer.style.cssText = "font-family: inherit; font-size: 12px; min-width: 210px; padding: 4px;";

        const badgeWrap = document.createElement("div");
        badgeWrap.style.cssText = "display: flex; align-items: center; gap: 5px; margin-bottom: 5px;";
        badgeWrap.innerHTML = `
          <span style="font-size: 10px; font-weight: 700; padding: 2px 7px; border-radius: 6px; background-color: ${domain.color}18; color: ${domain.color}; border: 1px solid ${domain.color}40;">
            ${domain.iconText} ${domain.label}
          </span>
        `;
        popupContainer.appendChild(badgeWrap);

        const titleEl = document.createElement("div");
        titleEl.style.cssText = "font-weight: 800; color: #0f172a; font-size: 13.5px; line-height: 1.3; margin-bottom: 3px;";
        titleEl.textContent = node.name;
        popupContainer.appendChild(titleEl);

        const idEl = document.createElement("div");
        idEl.style.cssText = "font-size: 10px; color: #64748b; font-family: monospace; margin-bottom: 8px;";
        idEl.textContent = `Mã: ${node.node_id.slice(0, 18)}...`;
        popupContainer.appendChild(idEl);

        const btnGroup = document.createElement("div");
        btnGroup.style.cssText = "display: flex; flex-direction: column; gap: 5px;";

        // Nút chính: Tìm đường đến đây ngay lập tức!
        const btnFind = document.createElement("button");
        btnFind.type = "button";
        btnFind.style.cssText = "width: 100%; padding: 6px 10px; background: #2563eb; color: #fff; font-size: 11px; font-weight: 700; border: none; border-radius: 8px; cursor: pointer; display: flex; align-items: center; justify-content: center; gap: 5px;";
        btnFind.innerHTML = `<span>Tìm đường đến đây</span>`;
        btnFind.onclick = (e) => {
          e.stopPropagation();
          popup.remove();
          setSelectedNode(node);
          const currentStart = fromNode || (graph.nodes.find((n) => n.type === "hub")?.node_id ?? graph.nodes[0]?.node_id);
          handleFindPath(currentStart, node.node_id);
        };
        btnGroup.appendChild(btnFind);

        const secondaryBtns = document.createElement("div");
        secondaryBtns.style.cssText = "display: flex; gap: 4px;";

        const btnStart = document.createElement("button");
        btnStart.type = "button";
        btnStart.style.cssText = "flex: 1; padding: 4px 6px; background: #f8fafc; color: #334155; font-size: 10.5px; font-weight: 700; border: 1px solid #cbd5e1; border-radius: 6px; cursor: pointer;";
        btnStart.textContent = "🚩 Đặt xuất phát";
        btnStart.onclick = (e) => {
          e.stopPropagation();
          setFromNode(node.node_id);
          setSelectedNode(node);
          popup.remove();
        };
        secondaryBtns.appendChild(btnStart);

        const btnDest = document.createElement("button");
        btnDest.type = "button";
        btnDest.style.cssText = "flex: 1; padding: 4px 6px; background: #f8fafc; color: #334155; font-size: 10.5px; font-weight: 700; border: 1px solid #cbd5e1; border-radius: 6px; cursor: pointer;";
        btnDest.textContent = "🏁 Đặt điểm đến";
        btnDest.onclick = (e) => {
          e.stopPropagation();
          setToNode(node.node_id);
          setSelectedNode(node);
          popup.remove();
        };
        secondaryBtns.appendChild(btnDest);

        btnGroup.appendChild(secondaryBtns);
        popupContainer.appendChild(btnGroup);

        const popup = new mapboxgl.Popup({ offset: 16, closeButton: true, maxWidth: "250px" }).setDOMContent(popupContainer);

        const marker = new mapboxgl.Marker({ element: el, anchor: "bottom" })
          .setLngLat([node.lng, node.lat])
          .setPopup(popup)
          .addTo(map);

        el.addEventListener("click", () => {
          setSelectedNode(node);
        });

        markersRef.current[node.node_id] = { marker, element: el, category };
      });
    });
  }, [graph, fromNode, toNode, getNodeCategory]);

  // Cập nhật hiển thị theo bộ lọc Domain (Ẩn mờ các điểm không thuộc bộ lọc)
  useEffect(() => {
    Object.values(markersRef.current).forEach(({ element, category }) => {
      if (filterCategory === "all" || category === filterCategory) {
        element.style.opacity = "1";
        element.style.filter = "none";
        element.style.pointerEvents = "auto";
      } else {
        element.style.opacity = "0.28";
        element.style.filter = "grayscale(60%)";
        element.style.pointerEvents = "auto";
      }
    });
  }, [filterCategory]);

  // Bay camera tới bước chỉ dẫn
  const handleFocusStep = (location: [number, number]) => {
    if (!mapRef.current || !location || (location[0] === 0 && location[1] === 0)) return;
    mapRef.current.flyTo({
      center: location,
      zoom: 17,
      speed: 1.2,
      curve: 1.4,
      essential: true,
    });
  };

  // Helper hiển thị icon định hướng cho từng bước chỉ dẫn
  const renderManeuverIcon = (type: string, modifier?: string) => {
    if (type === "arrive") {
      return (
        <svg className="w-4 h-4 text-rose-600 shrink-0" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round">
          <path d="M4 15s1-1 4-1 5 2 8 2 4-1 4-1V3s-1 1-4 1-5-2-8-2-4 1-4 1z" />
          <line x1="4" y1="22" x2="4" y2="15" />
        </svg>
      );
    }
    if (type === "depart") {
      return (
        <svg className="w-4 h-4 text-emerald-600 shrink-0" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round">
          <circle cx="12" cy="12" r="8" />
          <path d="M12 8v8" />
          <path d="M8 12h8" />
        </svg>
      );
    }
    if (modifier?.includes("right")) {
      return (
        <svg className="w-4 h-4 text-blue-600 shrink-0" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round">
          <path d="M9 18l6-6-6-6" />
        </svg>
      );
    }
    if (modifier?.includes("left")) {
      return (
        <svg className="w-4 h-4 text-blue-600 shrink-0" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round">
          <path d="M15 18l-6-6 6-6" />
        </svg>
      );
    }
    return (
      <svg className="w-4 h-4 text-slate-600 shrink-0" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round">
        <path d="M12 19V5" />
        <path d="M5 12l7-7 7 7" />
      </svg>
    );
  };

  const poiNodes = graph?.nodes.filter((n) => n.type === "poi" || n.type === "hub") ?? [];

  // Nhóm các điểm theo danh mục domain để hiển thị trong select
  const groupedNodes: Record<string, NodeData[]> = {};
  poiNodes.forEach((node) => {
    const cat = getNodeCategory(node);
    if (!groupedNodes[cat]) groupedNodes[cat] = [];
    groupedNodes[cat].push(node);
  });

  return (
    <div className="h-full flex flex-col gap-2.5 overflow-hidden">
      {/* Header thanh điều hướng */}
      <div className="flex items-center justify-between gap-4 shrink-0">
        <div>
          <h2 className="text-xl font-black text-slate-900 tracking-tight flex items-center gap-2">
            <span>Bản Đồ POI &amp; Dẫn Đường Thực Tế</span>
            <span className="text-[11px] font-bold px-2 py-0.5 rounded-full bg-blue-50 text-blue-700 border border-blue-200">
              Google Maps Style
            </span>
          </h2>
          <p className="text-xs text-slate-500 font-medium">
            Phân loại địa điểm bằng màu sắc &amp; biểu tượng trực quan, dẫn đường bám sát lối đi thực tế Mapbox
          </p>
        </div>

        {routeResult && (
          <button
            type="button"
            onClick={clearCurrentRoute}
            className="text-xs font-semibold px-3 py-1.5 rounded-lg border border-slate-200 text-slate-600 hover:bg-slate-100 transition cursor-pointer"
          >
            Xóa lộ trình
          </button>
        )}
      </div>

      {/* Thanh bộ lọc danh mục (Google Maps Category Chips) */}
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
          <span>Tất cả POI ({poiNodes.length})</span>
        </button>

        {Object.entries(DOMAIN_CONFIG).map(([key, cfg]) => {
          const count = groupedNodes[key]?.length ?? 0;
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
          <div className="absolute bottom-3 left-3 bg-white/95 backdrop-blur-xs px-3 py-2 rounded-xl text-[11px] border border-slate-200 shadow-md flex flex-wrap items-center gap-2.5 max-w-[80%]">
            <span className="font-bold text-slate-700 text-[10px] uppercase tracking-wider mr-1">Phân loại:</span>
            {Object.entries(DOMAIN_CONFIG).map(([k, cfg]) => (
              <span key={k} className="flex items-center gap-1 font-semibold text-slate-700 text-[10.5px]">
                <span
                  className="w-2.5 h-2.5 rounded-full inline-block"
                  style={{ backgroundColor: cfg.color }}
                />
                {cfg.label}
              </span>
            ))}
          </div>
        </div>

        {/* Cột Phải: Bảng tìm đường & Chỉ dẫn từng bước (Turn-by-Turn) */}
        <div className="w-full lg:w-96 bg-white rounded-2xl border border-slate-200 shadow-xs flex flex-col overflow-hidden h-full shrink-0">
          {/* Header chọn điểm & phương tiện */}
          <div className="p-3.5 border-b border-slate-100 space-y-2.5 shrink-0 bg-slate-50/70">
            <div className="flex items-center justify-between">
              <h3 className="text-xs font-extrabold uppercase tracking-wider text-slate-800">
                Tìm Tuyến Đường Thực Tế
              </h3>
              {/* Toggle phương tiện */}
              <div className="inline-flex bg-slate-200 p-0.5 rounded-lg text-[11px] font-semibold">
                <button
                  type="button"
                  onClick={() => setTravelMode("walking")}
                  className={`px-2 py-1 rounded-md transition cursor-pointer ${
                    travelMode === "walking" ? "bg-white text-blue-700 shadow-xs font-bold" : "text-slate-600"
                  }`}
                >
                  Đi bộ
                </button>
                <button
                  type="button"
                  onClick={() => setTravelMode("driving")}
                  className={`px-2 py-1 rounded-md transition cursor-pointer ${
                    travelMode === "driving" ? "bg-white text-blue-700 shadow-xs font-bold" : "text-slate-600"
                  }`}
                >
                  Xe buggy
                </button>
                <button
                  type="button"
                  onClick={() => setTravelMode("cycling")}
                  className={`px-2 py-1 rounded-md transition cursor-pointer ${
                    travelMode === "cycling" ? "bg-white text-blue-700 shadow-xs font-bold" : "text-slate-600"
                  }`}
                >
                  Xe đạp
                </button>
              </div>
            </div>

            <div className="space-y-2">
              <div>
                <label className="text-[11px] font-bold text-slate-600 mb-1 block">Từ điểm xuất phát:</label>
                <select
                  value={fromNode}
                  onChange={(e) => setFromNode(e.target.value)}
                  className="w-full text-xs p-2 rounded-xl border border-slate-200 bg-white font-medium text-slate-800 focus:outline-none focus:border-blue-600"
                >
                  {Object.entries(groupedNodes).map(([cat, nodes]) => (
                    <optgroup key={cat} label={`${DOMAIN_CONFIG[cat]?.iconText || "📍"} ${DOMAIN_CONFIG[cat]?.label || cat}`}>
                      {nodes.map((n) => (
                        <option key={n.node_id} value={n.node_id}>
                          {n.name}
                        </option>
                      ))}
                    </optgroup>
                  ))}
                </select>
              </div>

              <div>
                <label className="text-[11px] font-bold text-slate-600 mb-1 block">Đến điểm đích:</label>
                <select
                  value={toNode}
                  onChange={(e) => setToNode(e.target.value)}
                  className="w-full text-xs p-2 rounded-xl border border-slate-200 bg-white font-medium text-slate-800 focus:outline-none focus:border-blue-600"
                >
                  {Object.entries(groupedNodes).map(([cat, nodes]) => (
                    <optgroup key={cat} label={`${DOMAIN_CONFIG[cat]?.iconText || "📍"} ${DOMAIN_CONFIG[cat]?.label || cat}`}>
                      {nodes.map((n) => (
                        <option key={n.node_id} value={n.node_id}>
                          {n.name}
                        </option>
                      ))}
                    </optgroup>
                  ))}
                </select>
              </div>

              <div className="flex items-center gap-2 pt-1">
                <button
                  type="button"
                  onClick={() => {
                    const temp = fromNode;
                    setFromNode(toNode);
                    setToNode(temp);
                  }}
                  className="px-2.5 py-2 rounded-xl border border-slate-200 hover:bg-slate-100 text-slate-700 text-xs font-semibold transition cursor-pointer"
                  title="Đổi chiều xuất phát - điểm đến"
                >
                  ⇄
                </button>
                <button
                  type="button"
                  onClick={() => handleFindPath()}
                  disabled={loading}
                  className="flex-1 py-2 px-3 bg-blue-600 hover:bg-blue-700 active:bg-blue-800 disabled:opacity-50 text-white rounded-xl text-xs font-bold transition shadow-xs cursor-pointer text-center"
                >
                  {loading ? "Đang tìm đường..." : "Tìm đường đi thực tế"}
                </button>
              </div>

              {errorMsg && (
                <div className="p-2 rounded-lg bg-rose-50 border border-rose-200 text-rose-700 text-xs">
                  {errorMsg}
                </div>
              )}
            </div>
          </div>

          {/* Vùng kết quả chi tiết cuộn độc lập bên trong */}
          <div className="flex-1 overflow-y-auto p-3.5 space-y-3">
            {routeResult ? (
              <div className="space-y-3">
                {/* Thống kê lộ trình */}
                <div className="p-3 rounded-xl bg-blue-50 border border-blue-200 text-xs space-y-1.5">
                  <div className="flex items-center justify-between font-bold text-blue-900">
                    <span>Thời gian dự kiến:</span>
                    <span className="text-sm font-mono">{routeResult.durationMinutes} phút</span>
                  </div>
                  <div className="flex items-center justify-between text-blue-800">
                    <span>Khoảng cách thực tế:</span>
                    <span className="font-mono font-semibold">
                      {routeResult.distanceMeters >= 1000
                        ? `${(routeResult.distanceMeters / 1000).toFixed(1)} km`
                        : `${routeResult.distanceMeters} m`}
                    </span>
                  </div>
                  <div className="flex items-center justify-between text-blue-800 text-[11px]">
                    <span>Phương thức:</span>
                    <span className="font-semibold capitalize">
                      {routeResult.mode === "walking"
                        ? "Đi bộ"
                        : routeResult.mode === "driving"
                        ? "Xe buggy / ô tô"
                        : "Xe đạp"}
                    </span>
                  </div>
                  {routeResult.isMapboxRoute && (
                    <div className="text-[10px] text-emerald-700 font-semibold pt-1 border-t border-blue-200/60 flex items-center gap-1">
                      <span className="w-1.5 h-1.5 rounded-full bg-emerald-500 inline-block" />
                      Lộ trình thực tế theo lối đi Mapbox Directions
                    </div>
                  )}
                </div>

                {/* Danh sách các bước chỉ dẫn (Turn-by-Turn) */}
                {routeResult.steps.length > 0 && (
                  <div>
                    <h4 className="text-xs font-bold uppercase tracking-wider text-slate-700 mb-2">
                      Chỉ dẫn từng bước ({routeResult.steps.length} bước):
                    </h4>
                    <div className="space-y-1.5 border-l-2 border-blue-600/40 pl-3">
                      {routeResult.steps.map((step, idx) => (
                        <div
                          key={idx}
                          onClick={() => handleFocusStep(step.location)}
                          className="text-xs p-1.5 rounded-lg hover:bg-slate-100 transition cursor-pointer border border-transparent hover:border-slate-200"
                          title="Bấm để phóng to vị trí này trên bản đồ"
                        >
                          <div className="flex items-start gap-2">
                            <div className="mt-0.5">
                              {renderManeuverIcon(step.maneuverType, step.maneuverModifier)}
                            </div>
                            <div className="flex-1 min-w-0">
                              <div className="font-semibold text-slate-800 leading-snug">
                                {step.instruction}
                              </div>
                              {step.distance > 0 && (
                                <div className="text-[10px] text-slate-500 font-mono mt-0.5">
                                  Khoảng cách: {step.distance}m
                                </div>
                              )}
                            </div>
                          </div>
                        </div>
                      ))}
                    </div>
                  </div>
                )}
              </div>
            ) : selectedNode ? (
              <div className="p-3.5 rounded-xl bg-slate-50 border border-slate-200 text-xs space-y-2.5">
                <div className="flex items-center gap-1.5">
                  <span
                    className="w-2.5 h-2.5 rounded-full inline-block"
                    style={{ backgroundColor: DOMAIN_CONFIG[getNodeCategory(selectedNode)]?.color }}
                  />
                  <span className="text-[11px] font-bold text-slate-600">
                    {DOMAIN_CONFIG[getNodeCategory(selectedNode)]?.label}
                  </span>
                </div>
                <h4 className="font-extrabold text-slate-900 text-sm leading-tight">{selectedNode.name}</h4>
                <div className="text-slate-500 font-mono text-[11px]">ID: {selectedNode.node_id}</div>
                {selectedNode.lat && selectedNode.lng && (
                  <div className="text-slate-500 font-mono text-[11px]">
                    GPS: {selectedNode.lat.toFixed(5)}, {selectedNode.lng.toFixed(5)}
                  </div>
                )}

                {/* Nút bấm nhanh tra đường đến POI này */}
                <div className="pt-1 space-y-2">
                  <button
                    type="button"
                    onClick={() => {
                      setToNode(selectedNode.node_id);
                      handleFindPath(fromNode, selectedNode.node_id);
                    }}
                    className="w-full py-2 px-3 bg-blue-600 hover:bg-blue-700 active:bg-blue-800 text-white text-xs font-bold rounded-xl transition shadow-xs cursor-pointer flex items-center justify-center gap-1.5"
                  >
                    <span>Tìm đường đến {selectedNode.name}</span>
                  </button>

                  <div className="flex gap-2">
                    <button
                      type="button"
                      onClick={() => setFromNode(selectedNode.node_id)}
                      className="flex-1 py-1.5 px-2 bg-white hover:bg-slate-100 border border-slate-200 text-slate-800 text-[11px] font-bold rounded-lg transition cursor-pointer"
                    >
                      🚩 Đặt làm Xuất phát
                    </button>
                    <button
                      type="button"
                      onClick={() => setToNode(selectedNode.node_id)}
                      className="flex-1 py-1.5 px-2 bg-blue-50 hover:bg-blue-100 border border-blue-200 text-blue-700 text-[11px] font-bold rounded-lg transition cursor-pointer"
                    >
                      🏁 Đặt làm Điểm đến
                    </button>
                  </div>
                </div>
              </div>
            ) : (
              <div className="text-center py-10 text-slate-400 text-xs space-y-1">
                <div className="font-semibold text-slate-500">Chưa chọn tuyến đường</div>
                <p>Bấm vào bất kỳ ghim POI trên bản đồ hoặc chọn điểm từ danh sách để tìm đường đi thực tế.</p>
              </div>
            )}
          </div>
        </div>
      </div>
    </div>
  );
}
