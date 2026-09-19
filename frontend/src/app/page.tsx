"use client";

import React, { useState, useEffect, useRef } from "react";
import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";

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
  cost_breakdown?: {
    entry_ticket?: {
      ticket_type_label: string;
      total_vnd: number;
      items: Array<{ visitor_group: string; quantity: number; unit_price_vnd: number; subtotal_vnd: number }>;
    };
    addons_vnd: number;
  };
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

interface ClarificationQuestion {
  criteria_key: string;
  question: string;
  options: string[];
}

interface Clarification {
  message: string;
  questions: ClarificationQuestion[];
}

interface Message {
  role: "user" | "assistant";
  content: string;
  plans?: PlanOption[];
  isStreaming?: boolean;
}

function ClarificationWizard({
  clarification,
  disabled,
  onSubmit,
}: {
  clarification: Clarification;
  disabled: boolean;
  onSubmit: (message: string) => Promise<void>;
}) {
  const [step, setStep] = useState(0);
  const [answers, setAnswers] = useState<Record<string, string>>({});
  const [detailOption, setDetailOption] = useState<string | null>(null);
  const [detail, setDetail] = useState("");
  const [submitted, setSubmitted] = useState(false);
  const questions = clarification.questions;
  const current = questions[step];

  function saveAnswer(answer: string) {
    const nextAnswers = { ...answers, [current.criteria_key]: answer };
    setAnswers(nextAnswers);
    setDetailOption(null);
    setDetail("");
    if (step === questions.length - 1) {
      const summary = [
        "Thông tin bổ sung đã xác nhận:",
        ...questions.map((question) => `- ${question.question}: ${nextAnswers[question.criteria_key]}`),
      ].join("\n");
      setSubmitted(true);
      void onSubmit(summary);
      return;
    }
    setStep((value) => value + 1);
  }

  function selectOption(option: string) {
    if (option === "Khác/tự nhập" || option.includes("nhập")) {
      setDetailOption(option);
      setDetail("");
      return;
    }
    saveAnswer(option);
  }

  function saveDetail() {
    const value = detail.trim();
    if (!value || !detailOption) return;
    const prefix = detailOption === "Khác/tự nhập" || detailOption.includes("nhập số lượng")
      ? ""
      : `${detailOption.split("–")[0].trim()}: `;
    saveAnswer(`${prefix}${value}`);
  }

  function previousStep() {
    setDetailOption(null);
    setDetail("");
    setStep((value) => value - 1);
  }

  function nextStep() {
    if (!answers[current.criteria_key]) return;
    setStep((value) => value + 1);
  }

  if (submitted) {
    return (
      <div className="rounded-xl border border-[#d4d0c5] bg-[#faf9f6] p-4 text-xs text-[#71717a]">
        Đang gửi thông tin đã chọn…
      </div>
    );
  }

  return (
    <div className="rounded-xl border border-[#d4d0c5] bg-[#faf9f6] p-4 shadow-sm">
      <div className="mb-3 flex items-center justify-between gap-3">
        <p className="text-xs font-semibold text-[#18181b]">{current.question}</p>
        <div className="flex shrink-0 items-center gap-2 text-[11px] text-[#71717a]">
          <button
            type="button"
            disabled={step === 0 || disabled}
            onClick={previousStep}
            className="px-1 disabled:opacity-30"
            aria-label="Câu hỏi trước"
          >
            ‹
          </button>
          <span>{step + 1} trong {questions.length}</span>
          <button
            type="button"
            disabled={!answers[current.criteria_key] || disabled}
            onClick={nextStep}
            className="px-1 disabled:opacity-30"
            aria-label="Câu hỏi tiếp theo"
          >
            ›
          </button>
        </div>
      </div>

      {detailOption ? (
        <div className="flex gap-2">
          <input
            autoFocus
            value={detail}
            onChange={(event) => setDetail(event.target.value)}
            onKeyDown={(event) => event.key === "Enter" && saveDetail()}
            placeholder={current.criteria_key === "group_composition"
              ? "Ví dụ: 2 người lớn, 2 trẻ em"
              : "Nhập câu trả lời của bạn"}
            className="min-w-0 flex-1 rounded-lg border border-[#d4d0c5] px-3 py-2 text-xs outline-none focus:border-[#2563eb]"
          />
          <button
            type="button"
            disabled={!detail.trim() || disabled}
            onClick={saveDetail}
            className="rounded-lg bg-[#18181b] px-3 py-2 text-xs text-white disabled:opacity-30"
          >
            Tiếp
          </button>
        </div>
      ) : (
        <div className="max-h-64 divide-y divide-[#e6e3da] overflow-y-auto border-y border-[#e6e3da]">
          {current.options.map((option, index) => (
            <button
              key={option}
              type="button"
              disabled={disabled}
              onClick={() => selectOption(option)}
              className="flex w-full items-center gap-3 px-1 py-2.5 text-left text-xs text-[#27272a] transition hover:bg-[#faf9f6] disabled:cursor-not-allowed"
            >
              <span className="flex h-6 w-6 shrink-0 items-center justify-center rounded-md bg-[#f4f2eb] text-[11px] text-[#71717a]">
                {option === "Khác/tự nhập" ? "✎" : index + 1}
              </span>
              {option}
            </button>
          ))}
        </div>
      )}
    </div>
  );
}


export default function Home() {
  const [sessionId, setSessionId] = useState<string>("");
  const [messages, setMessages] = useState<Message[]>([]);
  const [events, setEvents] = useState<EventRecord[]>([]);
  const [inputMessage, setInputMessage] = useState<string>("");
  const [isStreaming, setIsStreaming] = useState<boolean>(false);
  const [activeClarification, setActiveClarification] = useState<Clarification | null>(null);
  const abortControllerRef = useRef<AbortController | null>(null);
  const [selectedEvent, setSelectedEvent] = useState<EventRecord | null>(null);
  const [copied, setCopied] = useState<boolean>(false);
  const [sidebarOpen, setSidebarOpen] = useState<boolean>(false);

  const chatEndRef = useRef<HTMLDivElement>(null);
  const textareaRef = useRef<HTMLTextAreaElement>(null);

  const adjustTextareaHeight = () => {
    const textarea = textareaRef.current;
    if (!textarea) return;
    textarea.style.height = "auto";
    const scrollH = textarea.scrollHeight;
    // Tự động mở rộng từ chiều cao tối thiểu 48px lên tối đa 240px
    const newHeight = Math.min(Math.max(scrollH, 48), 240);
    textarea.style.height = `${newHeight}px`;
    textarea.style.overflowY = scrollH > 240 ? "auto" : "hidden";
  };

  useEffect(() => {
    adjustTextareaHeight();
  }, [inputMessage]);

  useEffect(() => {
    createNewSession();
  }, []);

  useEffect(() => {
    chatEndRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages, isStreaming]);

  async function createNewSession() {
    if (abortControllerRef.current) {
      abortControllerRef.current.abort();
    }
    setIsStreaming(false);
    setActiveClarification(null);

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
              "Xin chào! Tôi là **Điều phối viên V-AI** tại VinWonders Nha Trang. Tôi có thể giúp gì cho chuyến tham quan của bạn hôm nay?",
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

  async function sendMessage(message: string) {
    if (!message.trim() || isStreaming) return;

    const userText = message.trim();
    setInputMessage("");
    setActiveClarification(null);

    // Thêm tin nhắn của User vào giao diện
    setMessages((prev) => [...prev, { role: "user", content: userText }]);
    setIsStreaming(true);

    // Thêm tin nhắn Assistant rỗng để nhận streaming tokens
    setMessages((prev) => [
      ...prev,
      { role: "assistant", content: "", isStreaming: true },
    ]);

    const abortController = new AbortController();
    abortControllerRef.current = abortController;

    try {
      const res = await fetch(`${API_BASE}/api/chat/stream`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          session_id: sessionId,
          message: userText,
        }),
        signal: abortController.signal,
      });

      if (!res.ok || !res.body) {
        throw new Error(`Lỗi kết nối máy chủ (${res.status})`);
      }

      const reader = res.body.getReader();
      const decoder = new TextDecoder("utf-8");
      let buffer = "";
      let accumulatedText = "";

      while (true) {
        const { done, value } = await reader.read();
        if (done) break;

        buffer += decoder.decode(value, { stream: true });
        const blocks = buffer.split("\n\n");
        buffer = blocks.pop() || "";

        for (const block of blocks) {
          if (!block.trim()) continue;
          const eventMatch = block.match(/event:\s*(\w+)/);
          const dataMatch = block.match(/data:\s*([\s\S]+)/);
          if (!eventMatch || !dataMatch) continue;

          const eventType = eventMatch[1];
          try {
            const data = JSON.parse(dataMatch[1]);

            if (eventType === "token") {
              accumulatedText += data.token;
              setMessages((prev) => {
                const copy = [...prev];
                const last = copy[copy.length - 1];
                if (last && last.role === "assistant") {
                  copy[copy.length - 1] = {
                    ...last,
                    content: accumulatedText,
                    isStreaming: true,
                  };
                }
                return copy;
              });
            } else if (eventType === "done") {
              setIsStreaming(false);
              setMessages((prev) => {
                const copy = [...prev];
                const last = copy[copy.length - 1];
                if (last && last.role === "assistant") {
                  copy[copy.length - 1] = {
                    ...last,
                    content: data.reply || accumulatedText,
                    plans: data.plans && data.plans.length > 0 ? data.plans : undefined,
                    isStreaming: false,
                  };
                }
                return copy;
              });
              setActiveClarification(
                data.clarification?.questions?.length ? data.clarification : null,
              );
              if (data.events) {
                setEvents(data.events);
              }
            }
          } catch (e) {
            console.warn("Lỗi parse SSE block:", e);
          }
        }
      }
    } catch (err: any) {
      if (err.name === "AbortError") {
        console.log("Stream dừng bởi người dùng.");
        setMessages((prev) => {
          const copy = [...prev];
          const last = copy[copy.length - 1];
          if (last && last.role === "assistant") {
            copy[copy.length - 1] = {
              ...last,
              content: last.content ? last.content + "\n\n*(Đã dừng tạo)*" : "*(Đã dừng tạo)*",
              isStreaming: false,
            };
          }
          return copy;
        });
      } else {
        console.error("Lỗi stream:", err);
        setMessages((prev) => {
          const copy = [...prev];
          const last = copy[copy.length - 1];
          if (last && last.role === "assistant") {
            copy[copy.length - 1] = {
              ...last,
              content: last.content
                ? last.content + "\n\n⚠️ *(Mất kết nối giữa chừng tới máy chủ)*"
                : "❌ Không thể kết nối tới Backend. Vui lòng kiểm tra tiến trình server.",
              isStreaming: false,
            };
          }
          return copy;
        });
      }
    } finally {
      setIsStreaming(false);
      abortControllerRef.current = null;
      setMessages((prev) =>
        prev.map((m) => (m.isStreaming ? { ...m, isStreaming: false } : m))
      );
    }
  }

  async function handleSend() {
    await sendMessage(inputMessage);
  }

  function handleStopGenerating() {
    if (abortControllerRef.current) {
      abortControllerRef.current.abort();
      setIsStreaming(false);
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
                <div key={idx} className="flex flex-col gap-2">
                  {m.role === "user" ? (
                    /* User Message Bubble */
                    <div className="self-end bg-[#18181b] text-white rounded-2xl px-4 py-3 text-sm leading-relaxed max-w-[85%] shadow-xs whitespace-pre-line">
                      {m.content}
                    </div>
                  ) : (
                    /* Assistant Message: Clean Modern Layout with Avatar & Status (No clunky box) */
                    <div className="self-start w-full flex items-start gap-3 py-1">
                      <div className="w-8 h-8 rounded-full bg-white border border-[#e6e3da] p-1 flex items-center justify-center shrink-0 shadow-2xs mt-0.5">
                        <img
                          src="/logo.png"
                          alt="V-AI"
                          className={`w-5 h-5 object-contain ${
                            m.isStreaming && !m.content ? "animate-pulse" : ""
                          }`}
                        />
                      </div>
                      <div className="flex-1 min-w-0 flex flex-col gap-1">
                        {/* Author Header */}
                        <div className="flex items-center gap-2">
                          <span className="font-bold text-sm text-[#2563eb]">V-AI</span>
                          {m.isStreaming && m.content && (
                            <span className="text-[11px] text-[#71717a] font-normal flex items-center gap-1">
                              <span className="w-1.5 h-1.5 rounded-full bg-blue-600 animate-pulse" />
                              Đang trả lời...
                            </span>
                          )}
                        </div>

                        {m.isStreaming && !m.content ? (
                          <div className="flex items-center gap-2 text-xs text-[#71717a] mt-0.5">
                            <span className="inline-flex gap-1 items-center" aria-hidden="true">
                              <span className="w-1.5 h-1.5 rounded-full bg-blue-600 animate-bounce [animation-delay:-0.3s]" />
                              <span className="w-1.5 h-1.5 rounded-full bg-blue-600 animate-bounce [animation-delay:-0.15s]" />
                              <span className="w-1.5 h-1.5 rounded-full bg-blue-600 animate-bounce" />
                            </span>
                            <span>V-AI đang suy nghĩ...</span>
                          </div>
                        ) : (
                          /* Rendered Streaming Markdown */
                          <div className="text-sm leading-relaxed text-[#18181b] break-words">
                            <ReactMarkdown
                              remarkPlugins={[remarkGfm]}
                              components={{
                                h1: ({ node, ...props }) => (
                                  <h1
                                    className="text-base font-bold text-[#18181b] mt-3 mb-1.5"
                                    {...props}
                                  />
                                ),
                                h2: ({ node, ...props }) => (
                                  <h2
                                    className="text-sm md:text-base font-bold text-[#18181b] mt-3 mb-1.5"
                                    {...props}
                                  />
                                ),
                                h3: ({ node, ...props }) => (
                                  <h3
                                    className="text-sm md:text-base font-bold text-[#18181b] mt-3 mb-1.5 pb-1 border-b border-[#e6e3da]"
                                    {...props}
                                  />
                                ),
                                h4: ({ node, ...props }) => (
                                  <h4
                                    className="text-xs md:text-sm font-bold text-[#18181b] mt-2 mb-1"
                                    {...props}
                                  />
                                ),
                                p: ({ node, ...props }) => (
                                  <p className="mb-2 last:mb-0 leading-relaxed text-sm text-[#27272a]" {...props} />
                                ),
                                ul: ({ node, ...props }) => (
                                  <ul
                                    className="list-disc pl-5 space-y-1 my-2 text-sm text-[#27272a]"
                                    {...props}
                                  />
                                ),
                                ol: ({ node, ...props }) => (
                                  <ol
                                    className="list-decimal pl-5 space-y-1 my-2 text-sm text-[#27272a]"
                                    {...props}
                                  />
                                ),
                                li: ({ node, ...props }) => (
                                  <li className="text-xs md:text-sm text-[#27272a] leading-relaxed" {...props} />
                                ),
                                strong: ({ node, ...props }) => (
                                  <strong className="font-semibold text-[#18181b]" {...props} />
                                ),
                                em: ({ node, ...props }) => (
                                  <em className="italic text-[#3f3f46]" {...props} />
                                ),
                                blockquote: ({ node, ...props }) => (
                                  <blockquote
                                    className="border-l-3 border-[#2563eb] pl-3 py-1 text-xs text-[#52525b] my-2 bg-[#f4f2eb]/50 rounded-r"
                                    {...props}
                                  />
                                ),
                                code: ({ node, className, children, ...props }) => (
                                  <code
                                    className="bg-[#f4f2eb] px-1.5 py-0.5 rounded text-xs font-mono text-[#18181b]"
                                    {...props}
                                  >
                                    {children}
                                  </code>
                                ),
                                table: ({ node, ...props }) => (
                                  <div className="overflow-x-auto my-3">
                                    <table className="min-w-full text-xs border border-[#e6e3da] divide-y divide-[#e6e3da]" {...props} />
                                  </div>
                                ),
                                th: ({ node, ...props }) => (
                                  <th className="bg-[#f4f2eb] px-3 py-1.5 text-left font-semibold text-[#18181b]" {...props} />
                                ),
                                td: ({ node, ...props }) => (
                                  <td className="px-3 py-1.5 border-t border-[#e6e3da] text-[#27272a]" {...props} />
                                ),
                              }}
                            >
                              {m.content
                                .replace(/^[ \t]*[•●○][ \t]+/gm, "- ")
                                .replace(/\n{3,}/g, "\n\n")}
                            </ReactMarkdown>
                          </div>
                        )}

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

                          {p.cost_breakdown?.entry_ticket && (
                            <div className="rounded-lg border border-[#e6e3da] bg-white p-2.5 text-[11px] text-[#52525b]">
                              <div className="font-semibold text-[#18181b]">
                                {p.cost_breakdown.entry_ticket.ticket_type_label}: {p.cost_breakdown.entry_ticket.total_vnd.toLocaleString("vi-VN")} VNĐ
                              </div>
                              <div className="mt-1">Các điểm vui chơi trong lịch: 0 VNĐ — đã bao gồm trong vé cổng.</div>
                              <div>Dịch vụ phát sinh chưa chọn: 0 VNĐ.</div>
                            </div>
                          )}

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
                </div>
              )}
            </div>
          ))}

              <div ref={chatEndRef} />
            </div>
          </div>

          {/* Chat Input Bar */}
          <div className="bg-[#faf9f6] px-4 pb-4 pt-2">
            <div className="max-w-3xl mx-auto space-y-2">
              {activeClarification && (
                <ClarificationWizard
                  clarification={activeClarification}
                  disabled={isStreaming}
                  onSubmit={sendMessage}
                />
              )}
              <div className="relative flex items-end">
              <textarea
                ref={textareaRef}
                value={inputMessage}
                onChange={(e) => setInputMessage(e.target.value)}
                onInput={adjustTextareaHeight}
                onKeyDown={(e) => {
                  if (e.key === "Enter" && !e.shiftKey) {
                    e.preventDefault();
                    handleSend();
                  }
                }}
                placeholder={
                  isStreaming
                    ? "V-AI đang trả lời, bạn có thể nhấn Dừng tạo..."
                    : "Cùng lập kế hoạch cho chuyến du lịch nào! (Enter để gửi, Shift+Enter xuống dòng)"
                }
                rows={1}
                disabled={isStreaming}
                style={{ minHeight: "48px", maxHeight: "240px" }}
                className="w-full bg-[#faf9f6] border border-[#e6e3da] focus:border-[#18181b] rounded-2xl pl-4 pr-24 py-3 text-sm text-[#18181b] placeholder-[#a1a1aa] focus:outline-none transition-colors resize-none leading-relaxed disabled:opacity-75"
              />

              {/* Nút Dừng tạo hoặc Nút Gửi - neo ở góc dưới bên phải */}
              {isStreaming ? (
                <button
                  type="button"
                  onClick={handleStopGenerating}
                  className="absolute right-3 bottom-2 px-3 py-1.5 rounded-full bg-[#18181b] hover:bg-red-600 text-white flex items-center gap-1.5 text-xs font-medium transition cursor-pointer shadow-xs group"
                  title="Dừng tạo phản hồi"
                >
                  <div className="w-2.5 h-2.5 bg-red-400 group-hover:bg-white rounded-xs transition" />
                  <span className="text-[11px]">Dừng tạo</span>
                </button>
              ) : (
                <button
                  type="button"
                  onClick={handleSend}
                  disabled={!inputMessage.trim()}
                  className="absolute right-3 bottom-1.5 w-9 h-9 rounded-full bg-[#18181b] hover:bg-[#27272a] disabled:opacity-25 text-white flex items-center justify-center transition cursor-pointer disabled:cursor-not-allowed shadow-xs"
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
              )}
              </div>
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
