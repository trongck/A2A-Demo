"use client";
import React, { useEffect, useState, useCallback } from "react";
import { useParams } from "next/navigation";
import Link from "next/link";
import { useAdminAuth } from "../../layout";
import { getApiBase } from "../../config";

function PlanCard({
  plan,
  planId,
  planStatus,
  adminNote,
  confirmedBy,
  onConfirm,
  onLoading,
}: any) {
  const [note, setNote] = useState(adminNote ?? "");

  const statusMap: any = {
    pending: "bg-amber-50 text-amber-700 border-amber-200",
    confirmed: "bg-emerald-50 text-emerald-700 border-emerald-200",
    rejected: "bg-rose-50 text-rose-700 border-rose-200",
  };

  return (
    <div
      className={`bg-white border rounded-2xl p-6 shadow-xs ${
        planStatus === "confirmed"
          ? "border-emerald-500/80 shadow-emerald-500/5 ring-1 ring-emerald-500/30"
          : "border-slate-200/80"
      }`}
    >
      <div className="flex items-center justify-between mb-4">
        <div>
          <h4 className="font-extrabold text-slate-900 text-base">
            {plan.style_label ?? plan.style ?? "Phương án lịch trình"}
          </h4>
          <p className="text-xs text-slate-500 font-medium mt-0.5">
            Tổng thời gian: {plan.total_duration_minutes} phút
          </p>
        </div>
        <span
          className={`text-xs px-3 py-1 rounded-full font-bold border ${
            statusMap[planStatus] ?? statusMap.pending
          }`}
        >
          {planStatus === "pending"
            ? "Chờ duyệt"
            : planStatus === "confirmed"
            ? "Đã duyệt & xác nhận"
            : "Đã từ chối"}
        </span>
      </div>

      {plan.legs && (
        <div className="space-y-2 mb-4">
          <p className="text-xs font-bold text-slate-700 uppercase tracking-wider">
            Các chặng trải nghiệm:
          </p>
          <div className="space-y-1.5">
            {plan.legs.map((leg: any, i: number) => (
              <div
                key={i}
                className="flex items-center gap-3 text-xs bg-slate-50 p-2.5 rounded-xl border border-slate-200/60"
              >
                <span className="w-5 h-5 rounded-full bg-blue-600 text-white flex items-center justify-center font-bold text-[10px] shrink-0">
                  {i + 1}
                </span>
                <span className="text-slate-800 font-semibold flex-1 truncate">
                  {leg.service_name}
                </span>
                <span className="text-slate-500 font-medium shrink-0">
                  {leg.activity_duration_minutes} phút
                </span>
              </div>
            ))}
          </div>
        </div>
      )}

      <p className="text-xs font-semibold text-slate-600 mb-4">
        Chi phí dự kiến:{" "}
        <span className="text-slate-900 font-extrabold">
          {(plan.total_cost_vnd ?? 0).toLocaleString("vi-VN")} VNĐ
        </span>
      </p>

      {planStatus === "confirmed" && confirmedBy && (
        <div className="px-4 py-3 bg-emerald-50 border border-emerald-200 rounded-xl text-xs text-emerald-800 font-medium mb-3">
          <span className="font-bold">Đã xác nhận bởi:</span> {confirmedBy}
          {adminNote ? ` • Ghi chú: ${adminNote}` : ""}
        </div>
      )}

      {planStatus === "pending" && (
        <div className="space-y-3 pt-4 border-t border-slate-100">
          <textarea
            value={note}
            onChange={(e) => setNote(e.target.value)}
            placeholder="Ghi chú điều phối (ví dụ: Đã sắp xếp xe điện đón khách tại cổng)..."
            rows={2}
            className="w-full px-3.5 py-2.5 bg-white border border-slate-300 rounded-xl text-xs font-medium text-slate-900 placeholder-slate-400 outline-none focus:border-blue-600 focus:ring-1 focus:ring-blue-600 resize-none"
          />
          <button
            onClick={() => onConfirm(planId, note)}
            disabled={onLoading}
            className="w-full py-2.5 bg-emerald-600 hover:bg-emerald-700 disabled:opacity-50 text-white text-xs font-bold rounded-xl transition-all shadow-xs cursor-pointer"
          >
            {onLoading ? "Đang xử lý..." : "Xác nhận lịch trình này"}
          </button>
        </div>
      )}
    </div>
  );
}

export default function BookingDetailPage() {
  const params = useParams();
  const sessionId = params.sessionId as string;
  const { token } = useAdminAuth();
  const [detail, setDetail] = useState<any>(null);
  const [loading, setLoading] = useState(true);
  const [actionLoading, setActionLoading] = useState(false);
  const [rejectReason, setRejectReason] = useState("");
  const [showRejectForm, setShowRejectForm] = useState(false);
  const [toast, setToast] = useState<{ msg: string; type: "success" | "error" } | null>(null);

  const getEffectiveToken = () =>
    token || (typeof window !== "undefined" ? localStorage.getItem("admin_token") : null);

  const showToast = (msg: string, type: "success" | "error") => {
    setToast({ msg, type });
    setTimeout(() => setToast(null), 3500);
  };

  const fetchDetail = useCallback(async () => {
    const curToken = getEffectiveToken();
    if (!curToken || !sessionId) return;
    setLoading(true);
    try {
      const apiBase = getApiBase();
      const r = await fetch(`${apiBase}/admin/bookings/${sessionId}`, {
        headers: { Authorization: `Bearer ${curToken}` },
      });
      if (r.ok) setDetail(await r.json());
    } finally {
      setLoading(false);
    }
  }, [token, sessionId]);

  useEffect(() => {
    fetchDetail();
  }, [fetchDetail]);

  async function handleConfirm(planId: string, note: string) {
    const curToken = getEffectiveToken();
    if (!curToken) return;
    setActionLoading(true);
    try {
      const apiBase = getApiBase();
      const r = await fetch(`${apiBase}/admin/bookings/${sessionId}/confirm`, {
        method: "POST",
        headers: { Authorization: `Bearer ${curToken}`, "Content-Type": "application/json" },
        body: JSON.stringify({ plan_id: planId, note: note || null }),
      });
      if (r.ok) {
        showToast("Đã xác nhận lịch trình thành công!", "success");
        await fetchDetail();
      } else {
        const d = await r.json();
        showToast(d.detail ?? "Lỗi xác nhận lịch trình", "error");
      }
    } catch {
      showToast("Lỗi kết nối máy chủ.", "error");
    } finally {
      setActionLoading(false);
    }
  }

  async function handleReject() {
    const curToken = getEffectiveToken();
    if (!curToken) return;
    if (rejectReason.trim().length < 10) {
      showToast("Lý do từ chối phải có tối thiểu 10 ký tự.", "error");
      return;
    }
    setActionLoading(true);
    try {
      const apiBase = getApiBase();
      const r = await fetch(`${apiBase}/admin/bookings/${sessionId}/reject`, {
        method: "POST",
        headers: { Authorization: `Bearer ${curToken}`, "Content-Type": "application/json" },
        body: JSON.stringify({ reason: rejectReason.trim() }),
      });
      if (r.ok) {
        showToast("Đã từ chối phiên tư vấn này.", "success");
        setShowRejectForm(false);
        await fetchDetail();
      } else {
        const d = await r.json();
        showToast(d.detail ?? "Lỗi từ chối phiên", "error");
      }
    } catch {
      showToast("Lỗi kết nối máy chủ.", "error");
    } finally {
      setActionLoading(false);
    }
  }

  if (loading)
    return (
      <div className="flex items-center justify-center py-24">
        <div className="w-8 h-8 border-3 border-blue-600 border-t-transparent rounded-full animate-spin" />
      </div>
    );

  if (!detail)
    return (
      <div className="text-center py-24 text-slate-500 font-medium">
        Không tìm thấy thông tin phiên tư vấn này.
      </div>
    );

  const { messages, plans } = detail;
  const allPlans = (plans as any[]).flatMap((rec: any) =>
    (Array.isArray(rec.plans) ? rec.plans : [rec.plans]).map((p: any) => ({
      ...p,
      __planId: rec.plan_id,
      __adminStatus: rec.admin_status,
      __note: rec.admin_note,
      __confirmedBy: rec.admin_confirmed_by,
    }))
  );

  return (
    <div className="space-y-6">
      {toast && (
        <div
          className={`fixed top-6 right-6 z-50 px-5 py-3 rounded-xl shadow-lg text-xs font-bold text-white ${
            toast.type === "success" ? "bg-emerald-600" : "bg-rose-600"
          }`}
        >
          {toast.msg}
        </div>
      )}

      {/* Thanh công cụ đỉnh trang */}
      <div className="flex items-center justify-between gap-4 flex-wrap">
        <div className="flex items-center gap-3 min-w-0">
          <Link
            href="/admin/bookings"
            className="text-slate-600 hover:text-slate-900 text-xs font-bold px-3 py-1.5 rounded-xl border border-slate-200 bg-white hover:bg-slate-50 transition-colors shadow-2xs"
          >
            ← Quay lại danh sách
          </Link>
          <span className="text-slate-300">|</span>
          <span className="text-xs font-mono font-bold text-slate-800 truncate">
            {sessionId}
          </span>
        </div>
        <button
          onClick={() => setShowRejectForm((v) => !v)}
          className="px-4 py-2 bg-rose-50 hover:bg-rose-100 border border-rose-200 text-rose-700 text-xs rounded-xl font-bold transition-all cursor-pointer shadow-2xs"
        >
          Từ chối phiên tư vấn này
        </button>
      </div>

      {/* Form từ chối */}
      {showRejectForm && (
        <div className="bg-rose-50 border border-rose-200 rounded-2xl p-6 space-y-3">
          <h4 className="text-xs font-bold text-rose-800 uppercase tracking-wider">
            Lý do từ chối (tối thiểu 10 ký tự)
          </h4>
          <textarea
            value={rejectReason}
            onChange={(e) => setRejectReason(e.target.value)}
            placeholder="Nhập lý do từ chối phiên này để ghi nhận lịch sử..."
            rows={3}
            className="w-full px-4 py-3 bg-white border border-rose-300 rounded-xl text-slate-900 text-xs font-medium outline-none focus:border-rose-600 focus:ring-1 focus:ring-rose-600 resize-none"
          />
          <div className="flex gap-2">
            <button
              onClick={handleReject}
              disabled={actionLoading}
              className="px-5 py-2.5 bg-rose-600 hover:bg-rose-700 disabled:opacity-50 text-white text-xs font-bold rounded-xl transition-all shadow-xs cursor-pointer"
            >
              {actionLoading ? "Đang xử lý..." : "Xác nhận từ chối"}
            </button>
            <button
              onClick={() => setShowRejectForm(false)}
              className="px-5 py-2.5 bg-white hover:bg-slate-100 border border-slate-200 text-slate-700 text-xs font-bold rounded-xl transition-all cursor-pointer"
            >
              Hủy bỏ
            </button>
          </div>
        </div>
      )}

      {/* Bố cục 2 cột: Hội thoại bên trái & Lịch trình bên phải */}
      <div className="grid grid-cols-1 lg:grid-cols-5 gap-6">
        {/* Lịch sử trao đổi */}
        <div
          className="lg:col-span-2 bg-white border border-slate-200/80 rounded-2xl overflow-hidden flex flex-col shadow-xs"
          style={{ maxHeight: "75vh" }}
        >
          <div className="px-5 py-4 border-b border-slate-100 bg-slate-50/80 shrink-0">
            <h3 className="font-extrabold text-slate-900 text-sm">
              Lịch sử trao đổi ({messages.length} tin nhắn)
            </h3>
          </div>
          <div className="flex-1 overflow-y-auto p-5 space-y-3">
            {messages.map((m: any, i: number) => (
              <div
                key={i}
                className={`flex ${m.role === "user" ? "justify-end" : "justify-start"}`}
              >
                <div
                  className={`max-w-[85%] px-4 py-3 rounded-2xl text-xs ${
                    m.role === "user"
                      ? "bg-blue-600 text-white rounded-br-none shadow-xs"
                      : "bg-slate-100 border border-slate-200 text-slate-800 rounded-bl-none"
                  }`}
                >
                  <p className="whitespace-pre-wrap break-words leading-relaxed">{m.content}</p>
                  <p
                    className={`text-[10px] mt-1.5 font-semibold ${
                      m.role === "user" ? "text-blue-100" : "text-slate-400"
                    }`}
                  >
                    {new Date(m.created_at).toLocaleTimeString("vi-VN")}
                  </p>
                </div>
              </div>
            ))}
            {messages.length === 0 && (
              <p className="text-xs text-slate-400 text-center py-8">Chưa có tin nhắn nào</p>
            )}
          </div>
        </div>

        {/* Các phương án lịch trình */}
        <div className="lg:col-span-3 space-y-4 overflow-y-auto" style={{ maxHeight: "75vh" }}>
          <h3 className="font-extrabold text-slate-900 text-sm">
            {allPlans.length} Phương án lịch trình đề xuất
          </h3>
          {allPlans.length === 0 && (
            <div className="bg-white border border-slate-200/80 rounded-2xl p-8 text-center text-slate-400 text-xs font-medium">
              Chưa có phương án lịch trình nào được lưu cho phiên này.
            </div>
          )}
          {allPlans.map((plan: any, i: number) => (
            <PlanCard
              key={i}
              plan={plan}
              planId={plan.__planId}
              planStatus={plan.__adminStatus}
              adminNote={plan.__note}
              confirmedBy={plan.__confirmedBy}
              onConfirm={handleConfirm}
              onLoading={actionLoading}
            />
          ))}
        </div>
      </div>
    </div>
  );
}