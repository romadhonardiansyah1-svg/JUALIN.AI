// Sentry browser SDK. Inert unless NEXT_PUBLIC_SENTRY_DSN is set.
// No replayIntegration on purpose: it adds ~40KB to the client bundle.
import * as Sentry from "@sentry/nextjs";

const dsn = process.env.NEXT_PUBLIC_SENTRY_DSN;

if (dsn) {
  Sentry.init({
    dsn,
    environment: process.env.NEXT_PUBLIC_SENTRY_ENVIRONMENT || "development",
    tracesSampleRate: 0.05,
    sendDefaultPii: false,
    integrations: [],
  });
}

export const onRouterTransitionStart = Sentry.captureRouterTransitionStart;
