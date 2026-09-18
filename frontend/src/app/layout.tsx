import type { Metadata } from "next";
import { Plus_Jakarta_Sans, Outfit, JetBrains_Mono } from "next/font/google";
import "./globals.css";

const outfit = Outfit({
  variable: "--font-outfit",
  subsets: ["latin", "latin-ext"],
});

const plusJakarta = Plus_Jakarta_Sans({
  variable: "--font-plus-jakarta",
  subsets: ["latin", "vietnamese"],
});

const jetbrainsMono = JetBrains_Mono({
  variable: "--font-mono",
  subsets: ["latin"],
});

export const metadata: Metadata = {
  title: "V-AI Multi-Agent System - Hệ Thống Đa Tác Tử Lập Lịch Trình VinWonders",
  description:
    "Hệ thống đa tác tử thông minh V-AI kết hợp A0 Điều phối, A2 Phân tích Mật độ và A1 Lập lịch trình qua giao thức A2A và MCP Server. Khám phá lịch trình du lịch cá nhân hóa VinWonders thời gian thực.",
  keywords: [
    "V-AI",
    "Multi-Agent System",
    "A2A Protocol",
    "Model Context Protocol",
    "MCP",
    "VinWonders",
    "Agentic AI",
    "Lập lịch trình",
  ],
  authors: [{ name: "DeepMind Pair Programming Team" }],
  openGraph: {
    title: "V-AI Multi-Agent System - Lập Lịch Trình VinWonders Chuẩn A2A & MCP",
    description:
      "Trực tiếp trải nghiệm và kiểm chứng giao tiếp Agent-to-Agent (A2A), MCP Server và Shared Memory SQLite.",
    type: "website",
  },
};

export default function RootLayout({
  children,
}: Readonly<{
  children: React.ReactNode;
}>) {
  return (
    <html
      lang="vi"
      className={`${outfit.variable} ${plusJakarta.variable} ${jetbrainsMono.variable} h-full`}
      suppressHydrationWarning
    >
      <body
        className="min-h-full flex flex-col bg-[#faf9f6] text-[#18181b] font-sans antialiased"
        suppressHydrationWarning
      >
        {children}
      </body>
    </html>

  );
}
