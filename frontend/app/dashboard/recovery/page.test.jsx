import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

vi.mock("@/lib/api", () => ({
  ApiError: class ApiError extends Error {},
  api: {
    getCapabilities: vi.fn(),
    getRecoveryOverview: vi.fn(),
    getRecoveryOpportunities: vi.fn(),
    getRecoveryOpportunity: vi.fn(),
    approveRecoveryOpportunity: vi.fn(),
    rejectRecoveryOpportunity: vi.fn(),
  },
}));

import { api } from "@/lib/api";
import RecoveryPage from "./page";

const pendingDetail = {
  id: "opp-1",
  state_version: 1,
  status: "awaiting_approval",
  can_decide: true,
  preview: { action_digest: "a".repeat(64), template_code: "payment_reminder_v1" },
  order: { amount: "10000", currency: "IDR" },
  recipient: { masked: "+62••••" },
  evidence: [],
};

describe("RecoveryPage decision feedback", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    api.getCapabilities.mockResolvedValue({
      capabilities: { payment_recovery: { enabled: true, paused: false, mode: "approval" } },
    });
    api.getRecoveryOverview.mockResolvedValue({ mode: "approval", counts: {} });
    api.getRecoveryOpportunities.mockResolvedValue({
      items: [{ id: "opp-1", order_id: 7, amount: "10000", status: "awaiting_approval" }],
    });
    api.getRecoveryOpportunity
      .mockResolvedValueOnce(pendingDetail)
      .mockResolvedValue({ ...pendingDetail, status: "dispatch_pending", can_decide: false });
    api.approveRecoveryOpportunity.mockResolvedValue({ message: "Persetujuan tersimpan." });
    api.rejectRecoveryOpportunity.mockResolvedValue({ message: "Peluang ditolak." });
  });

  it("keeps approve success visible after refreshing the detail", async () => {
    render(<RecoveryPage />);
    fireEvent.click(await screen.findByText("ORD-7"));
    fireEvent.click(await screen.findByRole("button", { name: "Setujui & jadwalkan" }));

    expect(await screen.findByText("Persetujuan tersimpan.")).toBeInTheDocument();
    await waitFor(() => expect(api.getRecoveryOpportunity).toHaveBeenCalledTimes(2));
    expect(screen.getByText("Persetujuan tersimpan.")).toBeInTheDocument();
  });

  it("keeps reject success visible after refreshing the detail", async () => {
    render(<RecoveryPage />);
    fireEvent.click(await screen.findByText("ORD-7"));
    fireEvent.click(await screen.findByRole("button", { name: "Lewati" }));

    expect(await screen.findAllByText("Peluang ditolak.")).toHaveLength(2);
    await waitFor(() => expect(api.getRecoveryOpportunity).toHaveBeenCalledTimes(2));
    expect(screen.getAllByText("Peluang ditolak.")).toHaveLength(2);
  });
});