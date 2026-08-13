import { withSentryConfig } from "@sentry/nextjs";

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

// Source map upload only runs when SENTRY_AUTH_TOKEN is present (CI); local and
// Docker builds stay unchanged.
export default withSentryConfig(nextConfig, {
  org: "university-of-nahdlatul-ulama",
  project: "jualin-frontend",
  silent: !process.env.CI,
  sourcemaps: { disable: !process.env.SENTRY_AUTH_TOKEN },
  telemetry: false,
  webpack: { treeshake: { removeDebugLogging: true } },
});
