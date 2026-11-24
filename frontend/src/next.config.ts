import type { NextConfig } from "next";

const nextConfig: NextConfig = {
  async redirects() {
    return [
      { source: "/product", destination: "/how-it-works", permanent: true },
      // Old links used a query string for the case id.
      { source: "/investigate", has: [{ type: "query", key: "investigation", value: "(?<id>.+)" }], destination: "/investigations/:id", permanent: false },
    ];
  },
};

export default nextConfig;
