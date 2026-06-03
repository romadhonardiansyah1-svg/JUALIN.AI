/** @type {import('next').NextConfig} */
const nextConfig = {
  // Rewrite /api/* to backend during development (proxy)
  async rewrites() {
    return [
      {
        source: "/api/:path*",
        destination: `${process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000"}/api/:path*`,
      },
      {
        source: "/uploads/:path*",
        destination: `${process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000"}/uploads/:path*`,
      },
    ];
  },
  // Output standalone for Docker deployment
  output: "standalone",
};

export default nextConfig;
