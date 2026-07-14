function statusValue(value) {
  return typeof value === "string" && value.length <= 64 ? value : "unknown";
}

export function buildSystemHealthRows(health) {
  const source = health && typeof health === "object" ? health : {};
  const schedulers = source.schedulers && typeof source.schedulers === "object"
    ? source.schedulers
    : {};

  return [
    { key: "backend", label: "Backend", value: statusValue(source.backend) },
    { key: "database", label: "Database", value: statusValue(source.database) },
    { key: "redis", label: "Redis", value: statusValue(source.redis) },
    { key: "ai_engine", label: "AI Engine", value: statusValue(source.ai_engine) },
    {
      key: "legacy_main",
      label: "Legacy Main Scheduler",
      value: statusValue(schedulers.legacy_main),
    },
    {
      key: "legacy_worker_cron",
      label: "Legacy Worker Cron",
      value: statusValue(schedulers.legacy_worker_cron),
    },
    {
      key: "recovery_scheduler",
      label: "Recovery Scheduler",
      value: statusValue(schedulers.recovery),
    },
  ];
}
