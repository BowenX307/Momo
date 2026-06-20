import type { NextConfig } from "next";

const nextConfig: NextConfig = {
  // Allow accessing the dev server through cloudflare quick tunnels (mobile testing).
  // Dev-only setting; has no effect on production builds.
  allowedDevOrigins: ["*.trycloudflare.com"],
};

export default nextConfig;
