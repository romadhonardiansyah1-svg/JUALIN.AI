const internalApiUrl =
  process.env.INTERNAL_API_URL ||
  process.env.NEXT_PUBLIC_API_URL ||
  "http://localhost:8000";

/** @type {import('next').NextConfig} */
const nextConfig = {
  // Rewrites are compiled at build time; Dockerfile supplies the container URL.
  async rewrites() {
    return [
      {
        source: "/api/:path*",
        destination: `${internalApiUrl}/api/:path*`,
      },
      {
        source: "/uploads/:path*",
        destination: `${internalApiUrl}/uploads/:path*`,
      },
    ];
  },
  // Output standalone for Docker deployment
  output: "standalone",
};

export default nextConfig;
