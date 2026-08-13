import * as Sentry from "@sentry/nextjs";

Sentry.init({
  dsn: process.env.SENTRY_DSN,
  environment: process.env.SENTRY_ENVIRONMENT || "development",
  tracesSampleRate: 0.05,
  sendDefaultPii: false,
});
