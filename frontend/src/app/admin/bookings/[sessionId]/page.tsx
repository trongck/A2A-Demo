"use client";
import { useEffect } from "react";
import { useRouter } from "next/navigation";

export default function BookingDetailPage() {
  const router = useRouter();

  useEffect(() => {
    router.replace("/admin/dashboard");
  }, [router]);

  return (
    <div className="flex items-center justify-center h-full text-slate-500 text-sm">
      Đang chuyển hướng về Bảng điều khiển...
    </div>
  );
}