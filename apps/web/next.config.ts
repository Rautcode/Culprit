import type { NextConfig } from "next";

const nextConfig: NextConfig = {
  // Self-contained server bundle at .next/standalone — what the container
  // image runs (apps/web/Dockerfile), no node_modules install at runtime.
  output: "standalone",
};

export default nextConfig;
