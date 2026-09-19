"use client";
import React, { useEffect, useState, useRef } from "react";
import { useAdminAuth } from "../layout";
import { getApiBase } from "../config";

interface GraphData {
  map_id: string;
  canvas_width_m: number;
  canvas_height_m: number;
  nodes: { node_id: string; name: string; x_m: number; y_m: number; type: string }[];
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

interface PathResult {
  path_nodes: string[];
  total_walking_minutes: number;
  total_distance_m: number;
}

const CATEGORY_NAMES: Record<string, string> = {
  ride: "Trò chơi giải trí",
  attraction: "Khu tham quan",
  food: "Ẩm thực & Nhà hàng",
  shop: "Cửa hàng",
  hotel: "Khách sạn / nghỉ dưỡng",
  service: "Dịch vụ",
  hub: "Điểm xuất phát",
  junction: "Nút giao thông",
};

export default function MapPage() {
  const { token } = useAdminAuth();
  const canvasRef = useRef<HTMLCanvasElement>(null);
  const [graph, setGraph] = useState<GraphData | null>(null);
  const [pathResult, setPathResult] = useState<PathResult | null>(null);
  const [fromNode, setFromNode] = useState("");
  const [toNode, setToNode] = useState("");
  const [pathLoading, setPathLoading] = useState(false);
  const [hoveredNode, setHoveredNode] = useState<string | null>(null);
  const [highlightPath, setHighlightPath] = useState<string[]>([]);

  const getEffectiveToken = () =>
    token || (typeof window !== "undefined" ? localStorage.getItem("admin_token") : null);

  useEffect(() => {
    const curToken = getEffectiveToken();
    const headers: Record<string, string> = curToken ? { Authorization: `Bearer ${curToken}` } : {};
    const apiBase = getApiBase();
    fetch(`${apiBase}/admin/map/graph`, { headers })
      .then((r) => r.json())
      .then((data: GraphData) => {
        setGraph(data);
        const start = data.nodes.find((node) => node.type === "hub")?.node_id ?? data.nodes[0]?.node_id ?? "";
        const destination = data.nodes.find((node) => node.type === "poi" && node.node_id !== start)?.node_id ?? "";
        setFromNode(start);
        setToNode(destination);
      })
      .catch(() => {});
  }, [token]);

  const W = 760;
  const H = 560;
  const PADDING = 70;

  function getScale(g: GraphData) {
    const sx = (W - PADDING * 2) / g.canvas_width_m;
    const sy = (H - PADDING * 2) / g.canvas_height_m;
    return Math.min(sx, sy);
  }
  function px(x: number, g: GraphData) {
    return PADDING + x * getScale(g);
  }
  function py(y: number, g: GraphData) {
    return PADDING + y * getScale(g);
  }

  const nodeMap = graph ? Object.fromEntries(graph.nodes.map((n) => [n.node_id, n])) : {};

  useEffect(() => {
    if (!graph || !canvasRef.current) return;
    const canvas = canvasRef.current;
    const ctx = canvas.getContext("2d");
    if (!ctx) return;
    ctx.clearRect(0, 0, W, H);

    // Nền sáng tinh tế
    ctx.fillStyle = "#f8fafc";
    ctx.fillRect(0, 0, W, H);

    // Vẽ lưới tọa độ mờ
    ctx.strokeStyle = "#e2e8f0";
    ctx.lineWidth = 0.5;
    for (let x = 0; x < W; x += 40) {
      ctx.beginPath();
      ctx.moveTo(x, 0);
      ctx.lineTo(x, H);
      ctx.stroke();
    }
    for (let y = 0; y < H; y += 40) {
      ctx.beginPath();
      ctx.moveTo(0, y);
      ctx.lineTo(W, y);
      ctx.stroke();
    }

    // Vẽ đường đi bộ (edges)
    graph.edges.forEach((e) => {
      const from = nodeMap[e.from_node_id];
      const to = nodeMap[e.to_node_id];
      if (!from || !to) return;
      const inPath =
        highlightPath.length > 1 &&
        highlightPath.some(
          (n, i) =>
            i < highlightPath.length - 1 &&
            ((highlightPath[i] === e.from_node_id && highlightPath[i + 1] === e.to_node_id) ||
              (highlightPath[i] === e.to_node_id && highlightPath[i + 1] === e.from_node_id))
        );

      ctx.beginPath();
      ctx.moveTo(px(from.x_m, graph), py(from.y_m, graph));
      ctx.lineTo(px(to.x_m, graph), py(to.y_m, graph));
      ctx.strokeStyle = inPath ? "#2563eb" : "#cbd5e1";
      ctx.lineWidth = inPath ? 3.5 : 1.5;
      ctx.lineCap = "round";
      ctx.stroke();

      if (inPath) {
        const mx = (px(from.x_m, graph) + px(to.x_m, graph)) / 2;
        const my = (py(from.y_m, graph) + py(to.y_m, graph)) / 2;
        ctx.fillStyle = "#1d4ed8";
        ctx.font = "bold 10px sans-serif";
        ctx.textAlign = "center";
        ctx.fillText(`${e.walking_minutes} phút`, mx, my - 6);
      }
    });

    // Vẽ các điểm (nodes)
    graph.nodes.forEach((n) => {
      const cx = px(n.x_m, graph);
      const cy = py(n.y_m, graph);
      const isHighlighted = highlightPath.includes(n.node_id);
      const isHovered = hoveredNode === n.node_id;

      if (n.type === "junction") {
        ctx.beginPath();
        ctx.arc(cx, cy, isHighlighted ? 5 : 3.5, 0, Math.PI * 2);
        ctx.fillStyle = isHighlighted ? "#2563eb" : "#94a3b8";
        ctx.fill();
      } else {
        const r = n.type === "hub" ? 11 : isHovered ? 10 : 8;
        ctx.beginPath();
        ctx.arc(cx, cy, r, 0, Math.PI * 2);
        const isStart = n.node_id === highlightPath[0];
        const isEnd = n.node_id === highlightPath[highlightPath.length - 1];
        ctx.fillStyle =
          n.type === "hub"
            ? "#d97706"
            : isStart || isEnd
            ? "#16a34a"
            : isHighlighted
            ? "#2563eb"
            : "#4f46e5";
        ctx.fill();

        ctx.strokeStyle = "#ffffff";
        ctx.lineWidth = 2.5;
        ctx.stroke();

        if (isHovered || isHighlighted) {
          ctx.strokeStyle = "#0f172a";
          ctx.lineWidth = 2;
          ctx.stroke();
        }

        // Tên điểm
        ctx.fillStyle = "#1e293b";
        ctx.font = "bold 9.5px sans-serif";
        ctx.textAlign = "center";
        const label = n.name.length > 14 ? n.name.slice(0, 14) + "…" : n.name;
        ctx.fillText(label, cx, cy + r + 13);
      }
    });
  }, [graph, highlightPath, hoveredNode]);

  function handleCanvasMouseMove(e: React.MouseEvent<HTMLCanvasElement>) {
    if (!graph || !canvasRef.current) return;
    const rect = canvasRef.current.getBoundingClientRect();
    const mx = (e.clientX - rect.left) * (W / rect.width);
    const my = (e.clientY - rect.top) * (H / rect.height);
    const hovered = graph.nodes.find((n) => {
      if (n.type === "junction") return false;
      const dx = mx - px(n.x_m, graph);
      const dy = my - py(n.y_m, graph);
      return Math.sqrt(dx * dx + dy * dy) < 14;
    });
    setHoveredNode(hovered?.node_id ?? null);
  }

  async function handleFindPath() {
    const curToken = getEffectiveToken();
    if (!curToken || !fromNode || !toNode) return;
    setPathLoading(true);
    try {
      const apiBase = getApiBase();
      const r = await fetch(
        `${apiBase}/admin/map/path?from_node=${encodeURIComponent(fromNode)}&to_node=${encodeURIComponent(toNode)}`,
        {
          headers: { Authorization: `Bearer ${curToken}` },
        }
      );
      if (r.ok) {
        const d = await r.json();
        setPathResult(d);
        setHighlightPath(d.path_nodes ?? []);
      }
    } catch {
    } finally {
      setPathLoading(false);
    }
  }

  const poiNodes = graph ? graph.nodes.filter((n) => n.type !== "junction") : [];

  return (
    <div className="space-y-6">
      <div>
        <h2 className="text-2xl font-black text-slate-900 tracking-tight">Bản đồ điều phối thông minh</h2>
        <p className="text-xs text-slate-500 font-medium mt-0.5">
          Tính toán đường đi ngắn nhất giữa các điểm vui chơi trong VinWonders Nha Trang
        </p>
      </div>

      <div className="grid grid-cols-1 xl:grid-cols-4 gap-6">
        {/* Canvas bản đồ */}
        <div className="xl:col-span-3 bg-white border border-slate-200/80 rounded-2xl p-6 shadow-xs">
          <div className="overflow-auto border border-slate-200 rounded-xl">
            <canvas
              ref={canvasRef}
              width={W}
              height={H}
              className="w-full h-auto block"
              style={{ cursor: hoveredNode ? "pointer" : "default" }}
              onMouseMove={handleCanvasMouseMove}
              onMouseLeave={() => setHoveredNode(null)}
            />
          </div>

          {/* Chi tiết khi rê chuột */}
          {hoveredNode && nodeMap[hoveredNode] && (
            <div className="mt-4 px-4 py-2.5 bg-slate-50 border border-slate-200 rounded-xl text-xs text-slate-800 inline-flex items-center gap-3">
              <span className="font-extrabold text-blue-700">{nodeMap[hoveredNode].name}</span>
              <span className="text-slate-400">|</span>
              <span className="font-mono text-slate-600">{hoveredNode}</span>
              {graph?.poi_metadata[hoveredNode] && (
                <>
                  <span className="text-slate-400">|</span>
                  <span className="font-semibold text-slate-700">
                    {CATEGORY_NAMES[graph.poi_metadata[hoveredNode].category] ??
                      graph.poi_metadata[hoveredNode].category}
                  </span>
                </>
              )}
            </div>
          )}

          {/* Kết quả tìm đường */}
          {pathResult && (
            <div className="mt-4 px-5 py-4 bg-blue-50 border border-blue-200 rounded-xl text-sm text-blue-950 flex items-start gap-4">
              <div>
                <p className="font-extrabold text-blue-900">
                  Lộ trình ngắn nhất: {pathResult.path_nodes.length} chặng dừng
                </p>
                <p className="text-xs text-blue-700 font-semibold mt-0.5">
                  Tổng thời gian: {pathResult.total_walking_minutes} phút đi bộ • Khoảng cách:{" "}
                  {pathResult.total_distance_m} mét
                </p>
                <p className="text-xs text-slate-600 mt-1 font-medium leading-relaxed">
                  {pathResult.path_nodes
                    .map((id) => nodeMap[id]?.name || id)
                    .join(" → ")}
                </p>
              </div>
            </div>
          )}
        </div>

        {/* Cột phải: Tìm đường & Chú giải */}
        <div className="space-y-6">
          {/* Bộ lọc tìm đường */}
          <div className="bg-white border border-slate-200/80 rounded-2xl p-6 shadow-xs">
            <h3 className="font-extrabold text-slate-900 text-base mb-4">Tìm lộ trình đi bộ</h3>
            <div className="space-y-4">
              <div>
                <label className="block text-xs font-bold text-slate-700 mb-1.5">Điểm xuất phát</label>
                <select
                  value={fromNode}
                  onChange={(e) => setFromNode(e.target.value)}
                  className="w-full px-3.5 py-2.5 bg-white border border-slate-300 rounded-xl text-slate-900 text-xs font-medium outline-none focus:border-blue-600 focus:ring-1 focus:ring-blue-600"
                >
                  {poiNodes.map((n) => (
                    <option key={n.node_id} value={n.node_id}>
                      {n.name}
                    </option>
                  ))}
                </select>
              </div>
              <div>
                <label className="block text-xs font-bold text-slate-700 mb-1.5">Điểm đến</label>
                <select
                  value={toNode}
                  onChange={(e) => setToNode(e.target.value)}
                  className="w-full px-3.5 py-2.5 bg-white border border-slate-300 rounded-xl text-slate-900 text-xs font-medium outline-none focus:border-blue-600 focus:ring-1 focus:ring-blue-600"
                >
                  {poiNodes
                    .filter((n) => n.node_id !== fromNode)
                    .map((n) => (
                      <option key={n.node_id} value={n.node_id}>
                        {n.name}
                      </option>
                    ))}
                </select>
              </div>
              <button
                onClick={handleFindPath}
                disabled={pathLoading || !fromNode || !toNode}
                className="w-full py-2.5 bg-blue-600 hover:bg-blue-700 disabled:opacity-50 text-white text-xs font-bold rounded-xl transition-all shadow-xs cursor-pointer"
              >
                {pathLoading ? "Đang tính toán lộ trình..." : "Vẽ đường đi ngắn nhất"}
              </button>
              {highlightPath.length > 0 && (
                <button
                  onClick={() => {
                    setHighlightPath([]);
                    setPathResult(null);
                  }}
                  className="w-full py-2 bg-slate-100 hover:bg-slate-200 text-slate-700 text-xs font-bold rounded-xl transition-all cursor-pointer"
                >
                  Xóa đường dẫn hiển thị
                </button>
              )}
            </div>
          </div>

          {/* Chú giải */}
          <div className="bg-white border border-slate-200/80 rounded-2xl p-6 shadow-xs">
            <h3 className="font-extrabold text-slate-900 text-base mb-4">Chú giải bản đồ</h3>
            <div className="space-y-3 text-xs text-slate-600 font-medium">
              {[
                ["#d97706", "Điểm xuất phát (Hub)"],
                ["#4f46e5", "Điểm vui chơi (POI)"],
                ["#16a34a", "Điểm bắt đầu / Điểm kết thúc"],
                ["#2563eb", "Nằm trên lộ trình ngắn nhất"],
                ["#94a3b8", "Nút giao thông đi bộ"],
              ].map(([color, label]) => (
                <div key={label} className="flex items-center gap-3">
                  <div className="w-3.5 h-3.5 rounded-full shrink-0" style={{ background: color as string }} />
                  <span>{label}</span>
                </div>
              ))}
              <div className="flex items-center gap-3 pt-1">
                <div className="w-8 h-1 bg-slate-300 shrink-0 rounded" />
                <span>Đường đi bộ kết nối</span>
              </div>
              <div className="flex items-center gap-3">
                <div className="w-8 h-1.5 bg-blue-600 shrink-0 rounded" />
                <span className="font-bold text-blue-700">Lộ trình tối ưu</span>
              </div>
            </div>
          </div>

          {/* Danh sách điểm đến */}
          <div className="bg-white border border-slate-200/80 rounded-2xl p-6 shadow-xs max-h-72 overflow-y-auto">
            <h3 className="font-extrabold text-slate-900 text-base mb-3">
              Danh sách điểm vui chơi ({poiNodes.length})
            </h3>
            <div className="space-y-1.5">
              {poiNodes.map((n) => (
                <button
                  key={n.node_id}
                  onClick={() => {
                    setFromNode(graph?.nodes.find((node) => node.type === "hub")?.node_id ?? "");
                    setToNode(n.node_id);
                  }}
                  className="w-full text-left px-3 py-2 rounded-xl hover:bg-slate-100 text-xs font-semibold text-slate-700 hover:text-slate-900 transition-colors flex items-center justify-between cursor-pointer"
                >
                  <span className="truncate">{n.name}</span>
                  <span className="text-[10px] text-slate-400 font-medium shrink-0 ml-2">Chọn làm đích</span>
                </button>
              ))}
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}
