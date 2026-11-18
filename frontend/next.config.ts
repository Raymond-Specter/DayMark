import type { NextConfig } from "next";
const nextConfig: NextConfig = {
  output: "standalone",
  experimental: { proxyClientMaxBodySize: 128 * 1024 * 1024 },
  async rewrites() {
    return [
      {
        source: "/api/:path*",
        destination: `${process.env.BACKEND_URL || "http://127.0.0.1:8000"}/api/:path*`,
      },
    ];
  },
  poweredByHeader: false,
};
export default nextConfig;
