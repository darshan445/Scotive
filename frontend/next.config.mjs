/** @type {import('next').NextConfig} */
const nextConfig = {
  reactStrictMode: true,
  // Keep Vite-era env names working alongside NEXT_PUBLIC_*
  env: {
    REACT_APP_BACKEND_URL:
      process.env.NEXT_PUBLIC_BACKEND_URL || process.env.REACT_APP_BACKEND_URL || "",
  },
  images: {
    remotePatterns: [],
    // Local public/ icons used as <img> already; allow unoptimized brand assets
  },
};

export default nextConfig;
