"use client";

import React, { useState, useEffect, useRef } from "react";

const API_BASE = "http://127.0.0.1:8000";

interface PlanLeg {
  step: number;
  service_id: string;
  service_name: string;
  node_id: string;
  arrival_time: string;
  start_time: string;
  end_time: string;
  walk_from_prev_minutes: number;
  wait_minutes: number;
  activity_duration_minutes: number;
  cost_vnd: number;
  indoor: boolean;
  note: string;
}

interface PlanOption {
  plan_id: string;
  style: string;
  style_label: string;
  total_duration_minutes: number;
  end_buffer_minutes: number;
  total_cost_vnd: number;
  return_arrival_time: string;
  legs: PlanLeg[];
  service_ids: string[];
  rationale: string;
}

interface EventRecord {
  event_id: string;
  session_id: string;
  turn_id: string;
  timestamp: string;
  event_type: string;
  sender: string;
  receiver: string;
  summary: string;
  payload: Record<string, any>;
  duration_ms: number;
  status: string;
  created_at: string;
}

interface Message {
  role: "user" | "assistant";
  content: string;
  plans?: PlanOption[];
}

export default function Home() {
  const [sessionId, setSessionId] = useState<string>("");
  const [messages, setMessages] = useState<Message[]>([]);
  const [events, setEvents] = useState<EventRecord[]>([]);
  const [inputMessage, setInputMessage] = useState<string>("");
  const [loading, setLoading] = useState<boolean>(false);
  const [selectedEvent, setSelectedEvent] = useState<EventRecord | null>(null);
  const [copied, setCopied] = useState<boolean>(false);
  const [sidebarOpen, setSidebarOpen] = useState<boolean>(true);

  const chatEndRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    createNewSession();
  }, []);

  useEffect(() => {
    chatEndRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages, loading]);

  async function createNewSession() {
    try {
      const res = await fetch(`${API_BASE}/api/session/new`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ scenario_id: "base" }),
      });
      if (res.ok) {
        const data = await res.json();
        setSessionId(data.session_id);
        setEvents([]);
        setSelectedEvent(null);
        setMessages([
          {
            role: "assistant",
            content:
              "Xin chào! Tôi là Điều phối viên V-AI. Tôi có thể giúp gì cho bạn !",
          },
        ]);
        refreshEvents(data.session_id);
      }
    } catch (err) {
      console.error("Lỗi tạo phiên:", err);
    }
  }

  async function refreshEvents(currentSid = sessionId) {
    if (!currentSid) return;
    try {
      const res = await fetch(`${API_BASE}/api/events/${currentSid}`);
      if (res.ok) {
        const data = await res.json();
        setEvents(data);
      }
    } catch (err) {
      console.warn("Lỗi tải log:", err);
    }
  }

  async function handleSend() {
    if (!inputMessage.trim() || loading) return;

    const userText = inputMessage.trim();
    setInputMessage("");
    setMessages((prev) => [...prev, { role: "user", content: userText }]);
    setLoading(true);

    try {
      const res = await fetch(`${API_BASE}/api/chat`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          session_id: sessionId,
          message: userText,
        }),
      });

      if (res.ok) {
        const data = await res.json();
        setLoading(false);
        setMessages((prev) => [
          ...prev,
          {
            role: "assistant",
            content: data.reply || "Đã xử lý xong yêu cầu của bạn.",
            plans: data.plans && data.plans.length > 0 ? data.plans : undefined,
          },
        ]);
        if (data.events) {
          setEvents(data.events);
        }
      } else {
        setLoading(false);
        setMessages((prev) => [
          ...prev,
          {
            role: "assistant",
            content: "❌ Đã có lỗi xảy ra khi kết nối máy chủ điều phối A0.",
          },
        ]);
      }
    } catch (err) {
      setLoading(false);
      setMessages((prev) => [
        ...prev,
        {
          role: "assistant",
          content:
            "Không thể kết nối tới Backend. Vui lòng kiểm tra tiến trình server.",
        },
      ]);
    }
  }

  function copyEventPayload() {
    if (selectedEvent) {
      navigator.clipboard.writeText(
        JSON.stringify(selectedEvent.payload, null, 2),
      );
      setCopied(true);
      setTimeout(() => setCopied(false), 2000);
    }
  }

  return (
    <div className="flex flex-col h-screen bg-[#faf9f6] text-[#18181b] overflow-hidden">
      {/* Top Minimalist Header */}
      <header className="bg-white border-b border-[#e6e3da] px-6 py-2.5 flex items-center justify-between shadow-xs">
        <div className="flex items-center gap-3">
          <img
            src="/logo.png"
            alt="V-AI Logo"
            className="w-8 h-8 object-contain"
          />
          <h1 className="text-base font-bold tracking-tight text-[#18181b]">
            V-AI
          </h1>
        </div>

        {/* Action */}
        <div className="flex items-center gap-3">
          <button
            onClick={() => createNewSession()}
            className="px-3 py-1.5 rounded-md bg-[#18181b] hover:bg-[#27272a] text-white text-xs font-medium transition cursor-pointer"
          >
            + Phiên mới
          </button>
        </div>
      </header>

      {/* Main Two-Column Layout */}
      <div className="flex-1 flex overflow-hidden">
        {/* Left Sidebar: Quick Log View (with collapse/expand) */}
        {sidebarOpen ? (
          <aside className="w-80 md:w-96 bg-[#f4f2eb] border-r border-[#e6e3da] flex flex-col overflow-hidden transition-all duration-300">
            <div className="p-3.5 border-b border-[#e6e3da] flex items-center justify-between">
              <div>
                <h2 className="text-xs font-bold uppercase tracking-wider text-[#18181b]">
                  Nhật Ký Tác Tử (A2A Trace)
                </h2>
                <p className="text-[11px] text-[#71717a]">
                  Click để xem nhanh payload trao đổi
                </p>
              </div>
              <div className="flex items-center gap-2">
                <span className="text-xs font-mono px-2 py-0.5 rounded-full bg-white border border-[#e6e3da] text-[#52525b]">
                  {events.length}
                </span>
                <button
                  onClick={() => setSidebarOpen(false)}
                  className="p-1 px-1.5 rounded-md hover:bg-white text-[#71717a] hover:text-[#18181b] text-xs transition cursor-pointer border border-transparent hover:border-[#e6e3da]"
                  title="Thu hẹp vào cạnh bên"
                >
                  ◀
                </button>
              </div>
            </div>

            {/* Log List */}
            <div className="flex-1 overflow-y-auto p-3 space-y-2">
              {events.length === 0 ? (
                <div className="text-center py-12 text-xs text-[#a1a1aa]">
                  Chưa có trao đổi nào. Hãy nhập tin nhắn để quan sát luồng Agent.
                </div>
              ) : (
                events.map((evt) => {
                  const isSelected = selectedEvent?.event_id === evt.event_id;
                  return (
                    <button
                      key={evt.event_id}
                      onClick={() => setSelectedEvent(evt)}
                      className={`w-full text-left p-3 rounded-lg border transition cursor-pointer ${
                        isSelected
                          ? "bg-white border-[#18181b] shadow-xs"
                          : "bg-white/80 hover:bg-white border-[#e6e3da] hover:border-[#d4d0c5]"
                      }`}
                    >
                      <div className="flex items-center justify-between mb-1">
                        <span className="font-mono text-xs font-bold text-[#2563eb]">
                          {evt.sender} ➔ {evt.receiver}
                        </span>
                        <span className="text-[10px] font-mono text-[#71717a]">
                          {evt.duration_ms} ms
                        </span>
                      </div>
                      <div className="text-xs text-[#27272a] line-clamp-2 leading-relaxed font-normal">
                        {evt.summary}
                      </div>
                      <div className="mt-1.5 flex items-center justify-between text-[10px] text-[#71717a]">
                        <span className="font-mono bg-[#f4f2eb] px-1.5 py-0.5 rounded border border-[#e6e3da]">
                          {evt.event_type}
                        </span>
                        <span
                          className={`font-semibold uppercase text-[9px] px-1.5 py-0.2 rounded ${
                            evt.status === "success"
                              ? "bg-emerald-50 text-emerald-700 border border-emerald-200"
                              : evt.status === "warning"
                                ? "bg-amber-50 text-amber-700 border border-amber-200"
                                : "bg-blue-50 text-blue-700 border border-blue-200"
                          }`}
                        >
                          {evt.status}
                        </span>
                      </div>
                    </button>
                  );
                })
              )}
            </div>
          </aside>
        ) : (
          <aside className="w-12 bg-[#f4f2eb] border-r border-[#e6e3da] flex flex-col items-center py-3 transition-all duration-300">
            <button
              onClick={() => setSidebarOpen(true)}
              className="p-1.5 rounded-md hover:bg-white text-[#71717a] hover:text-[#18181b] transition cursor-pointer mb-4"
              title="Mở rộng nhật ký A2A"
            >
              ▶
            </button>
            <div
              onClick={() => setSidebarOpen(true)}
              className="flex-1 flex flex-col items-center justify-center cursor-pointer select-none group"
            >
              <span className="[writing-mode:vertical-lr] text-[11px] font-bold uppercase tracking-wider text-[#52525b] group-hover:text-[#18181b] rotate-180 transition">
                Nhật Ký A2A
              </span>
              <span className="mt-3 text-[10px] font-mono font-bold px-1.5 py-0.5 rounded-full bg-white border border-[#e6e3da] text-[#2563eb]">
                {events.length}
              </span>
            </div>
          </aside>
        )}

        {/* Right Main Area: Chat & Plans */}
        <main className="flex-1 flex flex-col bg-[#faf9f6] overflow-hidden">
          {/* Chat Messages Feed */}
          <div className="flex-1 overflow-y-auto p-4 md:p-8 space-y-6">
            <div className="max-w-3xl mx-auto space-y-6">
              {messages.map((m, idx) => (
                <div key={idx} className="flex flex-col gap-3">
                  {/* Message Bubble */}
                  <div
                    className={`p-4 rounded-xl text-sm leading-relaxed max-w-[90%] ${
                      m.role === "user"
                        ? "self-end bg-[#18181b] text-white shadow-xs"
                        : "self-start bg-white border border-[#e6e3da] text-[#18181b] shadow-xs"
                    }`}
                  >
                    <div className="text-[11px] font-bold mb-1 opacity-70">
                      {m.role === "user" ? "Bạn" : "V-AI"}
                    </div>
                    <div
                      className="whitespace-pre-line"
                      dangerouslySetInnerHTML={{
                        __html: m.content
                          .replace(/\*\*(.*?)\*\*/g, "<strong>$1</strong>")
                          .replace(/^[•\-]\s+(.*)$/gm, "<li>$1</li>"),
                      }}
                    />
                  </div>

                  {/* Plan Cards Rendered Directly in Feed */}
                  {m.plans && m.plans.length > 0 && (
                    <div className="self-start w-full grid grid-cols-1 md:grid-cols-2 gap-4 my-2">
                      {m.plans.map((p) => (
                        <div
                          key={p.plan_id}
                          className="bg-white border border-[#e6e3da] rounded-xl p-4 shadow-xs flex flex-col gap-3 hover:border-[#18181b] transition"
                        >
                          <div className="flex items-start justify-between border-b border-[#f4f2eb] pb-2">
                            <div>
                              <h3 className="font-bold text-sm text-[#18181b]">
                                {p.style_label}
                              </h3>
                              <span className="text-[10px] font-bold uppercase tracking-wider text-emerald-700 bg-emerald-50 px-2 py-0.5 rounded border border-emerald-200">
                                {p.style}
                              </span>
                            </div>
                            <span className="text-xs font-bold text-emerald-600">
                              ✓ Đã duyệt
                            </span>
                          </div>

                          <div className="grid grid-cols-3 gap-2 bg-[#f4f2eb] p-2.5 rounded-lg text-center text-xs">
                            <div>
                              <span className="block font-bold text-[#18181b]">
                                {p.total_duration_minutes}p
                              </span>
                              <span className="text-[10px] text-[#71717a]">
                                Tổng thời gian
                              </span>
                            </div>
                            <div>
                              <span className="block font-bold text-emerald-600">
                                +{p.end_buffer_minutes}p
                              </span>
                              <span className="text-[10px] text-[#71717a]">
                                Dự phòng (≥10p)
                              </span>
                            </div>
                            <div>
                              <span className="block font-bold text-[#18181b]">
                                {p.total_cost_vnd
                                  ? p.total_cost_vnd.toLocaleString() + " đ"
                                  : "0 đ"}
                              </span>
                              <span className="text-[10px] text-[#71717a]">
                                Chi phí đoàn
                              </span>
                            </div>
                          </div>

                          <div className="text-xs text-[#52525b] bg-[#faf9f6] p-2.5 rounded-lg border-l-2 border-[#18181b] leading-relaxed">
                            {p.rationale}
                          </div>

                          {/* Legs Timeline */}
                          <div className="space-y-2 pt-2 border-t border-[#f4f2eb] text-xs">
                            <div className="font-bold text-[10px] uppercase text-[#71717a]">
                              Lộ trình các chặng:
                            </div>
                            {p.legs.map((leg) => (
                              <div
                                key={leg.step}
                                className="flex items-center gap-3"
                              >
                                <span className="font-mono font-bold text-[#2563eb] w-12 text-right">
                                  {leg.arrival_time}
                                </span>
                                <div className="flex-1 bg-[#faf9f6] p-2 rounded border border-[#e6e3da]">
                                  <div className="font-semibold text-[#18181b] flex justify-between">
                                    <span>
                                      {leg.step}. {leg.service_name}
                                    </span>
                                    <span
                                      className={`text-[9px] px-1.5 py-0.2 rounded ${
                                        leg.indoor
                                          ? "bg-blue-50 text-blue-700"
                                          : "bg-amber-50 text-amber-700"
                                      }`}
                                    >
                                      {leg.indoor ? "Trong nhà" : "Ngoài trời"}
                                    </span>
                                  </div>
                                  <div className="text-[10px] text-[#71717a] mt-0.5">
                                    Đi bộ: {leg.walk_from_prev_minutes}p • Chờ:{" "}
                                    {leg.wait_minutes}p • Chơi:{" "}
                                    {leg.activity_duration_minutes}p
                                  </div>
                                </div>
                              </div>
                            ))}

                            <div className="flex items-center gap-3 pt-1 border-t border-dashed border-[#e6e3da]">
                              <span className="font-mono font-bold text-emerald-600 w-12 text-right">
                                {p.return_arrival_time}
                              </span>
                              <div className="flex-1 bg-emerald-50 border border-emerald-200 p-2 rounded text-emerald-800 flex justify-between items-center text-[11px]">
                                <span>✓ Về lại Sea World Hub an toàn</span>
                                <span className="font-bold font-mono">
                                  Dư {p.end_buffer_minutes}p dự phòng
                                </span>
                              </div>
                            </div>
                          </div>
                        </div>
                      ))}
                    </div>
                  )}
                </div>
              ))}

              {loading && (
                <div className="self-start bg-white border border-[#e6e3da] rounded-xl p-3.5 flex items-center gap-3 text-xs text-[#52525b] shadow-xs">
                  <div className="w-4 h-4 border-2 border-[#18181b] border-t-transparent rounded-full animate-spin"></div>
                  <span className="font-mono">
                    Đang điều phối: <strong>A0</strong> ➔ <strong>A2</strong>{" "}
                    (Mật độ) ➔ <strong>A1</strong> (Lập lịch) ➔{" "}
                    <strong>Validator</strong>
                  </span>
                </div>
              )}
              <div ref={chatEndRef} />
            </div>
          </div>

          {/* Chat Input Bar */}
          <div className="bg-white border-t border-[#e6e3da] p-4">
            <div className="max-w-3xl mx-auto relative flex items-center">
              <textarea
                value={inputMessage}
                onChange={(e) => setInputMessage(e.target.value)}
                onKeyDown={(e) => {
                  if (e.key === "Enter" && !e.shiftKey) {
                    e.preventDefault();
                    handleSend();
                  }
                }}
                placeholder="Cùng lập kế hoạch cho chuyến du lịch nào! "
                rows={2}
                className="w-full bg-[#faf9f6] border border-[#e6e3da] focus:border-[#18181b] rounded-2xl pl-4 pr-14 py-3 text-sm text-[#18181b] placeholder-[#a1a1aa] focus:outline-none transition resize-none leading-relaxed"
              />
              <button
                onClick={handleSend}
                disabled={loading || !inputMessage.trim()}
                className="absolute right-3 top-1/2 -translate-y-1/2 w-9 h-9 rounded-full bg-[#18181b] hover:bg-[#27272a] disabled:opacity-25 text-white flex items-center justify-center transition cursor-pointer disabled:cursor-not-allowed shadow-xs"
                title="Gửi"
              >
                <svg
                  xmlns="http://www.w3.org/2000/svg"
                  viewBox="0 0 20 20"
                  fill="currentColor"
                  className="w-4 h-4 ml-0.5"
                >
                  <path d="M3.105 2.288a.75.75 0 0 0-.826.95l1.414 4.926A1.5 1.5 0 0 0 5.135 9.25h6.115a.75.75 0 0 1 0 1.5H5.135a1.5 1.5 0 0 0-1.442 1.086l-1.414 4.926a.75.75 0 0 0 .826.95 28.897 28.897 0 0 0 15.293-7.155.75.75 0 0 0 0-1.114A28.897 28.897 0 0 0 3.105 2.288Z" />
                </svg>
              </button>
            </div>
          </div>
        </main>
      </div>

      {/* Quick Payload Inspector Modal (Click from Left Sidebar) */}
      {selectedEvent && (
        <div
          className="fixed inset-0 z-50 bg-black/40 backdrop-blur-xs flex items-center justify-center p-4"
          onClick={() => setSelectedEvent(null)}
        >
          <div
            className="bg-white border border-[#e6e3da] rounded-xl max-w-2xl w-full max-h-[85vh] flex flex-col shadow-xl overflow-hidden"
            onClick={(e) => e.stopPropagation()}
          >
            <div className="px-5 py-3.5 border-b border-[#e6e3da] flex items-center justify-between bg-[#faf9f6]">
              <div>
                <h3 className="text-xs font-bold uppercase tracking-wider text-[#18181b]">
                  {selectedEvent.sender} ➔ {selectedEvent.receiver}
                </h3>
                <p className="text-[11px] text-[#71717a] font-mono">
                  {selectedEvent.event_type} • {selectedEvent.duration_ms} ms
                </p>
              </div>
              <button
                onClick={() => setSelectedEvent(null)}
                className="text-[#71717a] hover:text-[#18181b] text-base font-bold cursor-pointer"
              >
                ✕
              </button>
            </div>

            <div className="p-4 flex-1 overflow-y-auto bg-[#f4f2eb]/50">
              <pre className="font-mono text-xs text-[#18181b] bg-white p-4 rounded-lg border border-[#e6e3da] overflow-x-auto leading-relaxed">
                {JSON.stringify(selectedEvent.payload, null, 2)}
              </pre>
            </div>

            <div className="px-5 py-3 border-t border-[#e6e3da] bg-[#faf9f6] flex justify-end gap-2">
              <button
                onClick={copyEventPayload}
                className="px-3 py-1.5 rounded-md bg-white hover:bg-[#f4f2eb] border border-[#e6e3da] text-xs font-medium text-[#18181b] transition cursor-pointer"
              >
                {copied ? "Đã sao chép ✓" : "Sao chép JSON"}
              </button>
              <button
                onClick={() => setSelectedEvent(null)}
                className="px-3 py-1.5 rounded-md bg-[#18181b] hover:bg-[#27272a] text-xs font-semibold text-white transition cursor-pointer"
              >
                Đóng
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
