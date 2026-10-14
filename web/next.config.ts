import type { NextConfig } from "next";

const backend = (process.env.ACEPRESSURE_API_URL ?? "http://127.0.0.1:8765").replace(/\/$/, "");

const nextConfig: NextConfig = {
  reactStrictMode: true,
  poweredByHeader: false,
  async rewrites() {
    return [
      // Next is the public front door after cutover. Flask remains responsible
      // for the dashboard, overlays, static assets and services.
      { source: "/api/:path*", destination: `${backend}/api/:path*` },
      { source: "/media/:path*", destination: `${backend}/media/:path*` },
      { source: "/static/:path*", destination: `${backend}/static/:path*` },
      { source: "/admin/:path*", destination: `${backend}/admin/:path*` },
      { source: "/obs/:path*", destination: `${backend}/obs/:path*` },
      { source: "/overlay/:path*", destination: `${backend}/overlay/:path*` },
      { source: "/health", destination: `${backend}/health` }
    ];
  }
};

export default nextConfig;
