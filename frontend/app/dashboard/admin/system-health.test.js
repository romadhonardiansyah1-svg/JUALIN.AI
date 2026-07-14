import { describe, expect, it } from "vitest";

import { buildSystemHealthRows } from "./system-health";

describe("buildSystemHealthRows", () => {
  it("flattens per-owner scheduler state and never returns object values", () => {
    const rows = buildSystemHealthRows({
      backend: "online",
      database: "connected",
      redis: "connected",
      ai_engine: "ready",
      followup_scheduler: "disabled",
      schedulers: {
        legacy_main: "disabled",
        legacy_worker_cron: "not_registered",
        recovery: "registered_disabled",
      },
      flags: {
        scheduler_enabled: false,
        enable_legacy_pending_payment_followup: false,
      },
      version: "test",
    });

    expect(rows).toEqual([
      { key: "backend", label: "Backend", value: "online" },
      { key: "database", label: "Database", value: "connected" },
      { key: "redis", label: "Redis", value: "connected" },
      { key: "ai_engine", label: "AI Engine", value: "ready" },
      {
        key: "legacy_main",
        label: "Legacy Main Scheduler",
        value: "disabled",
      },
      {
        key: "legacy_worker_cron",
        label: "Legacy Worker Cron",
        value: "not_registered",
      },
      {
        key: "recovery_scheduler",
        label: "Recovery Scheduler",
        value: "registered_disabled",
      },
    ]);
    expect(rows.every(({ value }) => typeof value === "string")).toBe(true);
  });

  it("uses unknown scalar fallbacks for missing scheduler registry data", () => {
    const rows = buildSystemHealthRows(null);

    expect(rows).toHaveLength(7);
    expect(rows.every(({ value }) => value === "unknown")).toBe(true);
  });
});
