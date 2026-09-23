import type { NextConfig } from "next";

const nextConfig: NextConfig & { agentRules?: boolean } = {
  agentRules: false,
  distDir: process.env.NEXT_BUILD_DIR || ".next",
};

export default nextConfig;
