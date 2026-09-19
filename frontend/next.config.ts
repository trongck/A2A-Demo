import type { NextConfig } from "next";

const MAPBOX_DOMAINS = [
  "https://*.mapbox.com",
  "https://api.mapbox.com",
  "https://events.mapbox.com",
].join(" ");

const CSP = [
  "default-src 'self'",
  `script-src 'self' 'unsafe-eval' 'unsafe-inline' blob: ${MAPBOX_DOMAINS}`,
  `worker-src blob: ${MAPBOX_DOMAINS}`,
  `child-src blob: ${MAPBOX_DOMAINS}`,
  `style-src 'self' 'unsafe-inline' ${MAPBOX_DOMAINS}`,
  `img-src 'self' data: blob: https: http:`,
  `font-src 'self' data: https://fonts.gstatic.com ${MAPBOX_DOMAINS}`,
  `connect-src 'self' http://127.0.0.1:* http://localhost:* ws://127.0.0.1:* ws://localhost:* ${MAPBOX_DOMAINS}`,
].join("; ");

const nextConfig: NextConfig = {
  async headers() {
    return [
      {
        source: "/(.*)",
        headers: [
          {
            key: "Content-Security-Policy",
            value: CSP,
          },
        ],
      },
    ];
  },
};

export default nextConfig;
