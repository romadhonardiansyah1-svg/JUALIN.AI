import { render, screen, waitFor } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

vi.mock("next/navigation", () => ({
  useParams: () => ({ orderId: "77" }),
  useSearchParams: () => ({ get: () => "" }),
}));
vi.mock("@/lib/api", () => ({
  api: {
    exchangePublicCapability: vi.fn(),
    getPublicPaymentStatusViaSession: vi.fn().mockResolvedValue({
      order_id: 77,
      status: "pending",
      provider: "retired-provider",
      amount: 100000,
      payment_created: false,
      migration_required: true,
      payment_error: "Provider pembayaran lama telah dihentikan.",
    }),
    getPublicPaymentMethodsViaSession: vi.fn().mockResolvedValue({
      methods: [{ provider: "midtrans", method: "snap", label: "Midtrans" }],
    }),
    createPublicPaymentViaSession: vi.fn(),
    grantReminderConsent: vi.fn(),
  },
}));

import { api } from "@/lib/api";
import PaymentPage from "./page";

describe("PaymentPage retired provider", () => {
  it("shows migration guidance without offering payment actions", async () => {
    render(<PaymentPage />);

    expect(await screen.findByText("Provider pembayaran lama telah dihentikan.")).toBeInTheDocument();
    await waitFor(() => expect(api.getPublicPaymentStatusViaSession).toHaveBeenCalled());
    expect(api.getPublicPaymentMethodsViaSession).not.toHaveBeenCalled();
    expect(screen.queryByText("Buat Pembayaran")).not.toBeInTheDocument();
    expect(screen.queryByText("Pengingat Pembayaran")).not.toBeInTheDocument();
  });
});