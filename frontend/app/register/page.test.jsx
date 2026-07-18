import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

const push = vi.fn();
const login = vi.fn().mockResolvedValue(undefined);
vi.mock("next/navigation", () => ({
  useRouter: () => ({ push }),
  useSearchParams: () => ({ get: (key) => key === "ref" ? "REF-SELLER-1234" : "" }),
}));
vi.mock("@/components/AuthProvider", () => ({ useAuth: () => ({ login }) }));
vi.mock("@/lib/api", () => ({ api: { register: vi.fn().mockResolvedValue({}) } }));

import { api } from "@/lib/api";
import RegisterPage from "./page";

describe("RegisterPage referral attribution", () => {
  it("sends the referral code from the generated registration link", async () => {
    render(<RegisterPage />);
    fireEvent.change(screen.getByPlaceholderText("Contoh: Toko Sari Fashion"), {
      target: { value: "Toko Baru" },
    });
    fireEvent.change(screen.getByPlaceholderText("email@tokoku.com"), {
      target: { value: "baru@example.com" },
    });
    fireEvent.change(screen.getByPlaceholderText("Minimal 10 karakter"), {
      target: { value: "password-aman" },
    });
    fireEvent.submit(screen.getByPlaceholderText("Minimal 10 karakter").closest("form"));

    await waitFor(() => expect(api.register).toHaveBeenCalled());
    expect(api.register).toHaveBeenCalledWith(expect.objectContaining({
      referral_code: "REF-SELLER-1234",
    }));
  });
});
