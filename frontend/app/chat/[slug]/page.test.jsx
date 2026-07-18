import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

vi.mock("next/navigation", () => ({ useParams: () => ({ slug: "toko-uji" }) }));
vi.mock("@/lib/api", () => ({
  api: { getChatHistory: vi.fn(), sendChat: vi.fn() },
  sendChatStream: vi.fn(),
}));

import { api, sendChatStream } from "@/lib/api";
import PublicChatPage from "./page";

describe("PublicChatPage stream recovery", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    vi.spyOn(console, "error").mockImplementation(() => {});
    sessionStorage.clear();
    Element.prototype.scrollIntoView = vi.fn();
    api.getChatHistory.mockResolvedValue({ messages: [] });
    api.sendChat.mockResolvedValue({ response: "duplicate response" });
  });

  afterEach(() => vi.restoreAllMocks());

  it("does not replay a committed streaming turn through REST after a read failure", async () => {
    sendChatStream.mockImplementation(({ onError }) => {
      onError(new Error("stream disconnected"));
      return vi.fn();
    });

    render(<PublicChatPage />);
    fireEvent.change(screen.getByPlaceholderText("Ketik pesan..."), {
      target: { value: "Saya mau beli" },
    });
    fireEvent.submit(screen.getByPlaceholderText("Ketik pesan...").closest("form"));

    await waitFor(() => expect(sendChatStream).toHaveBeenCalledOnce());
    expect(api.sendChat).not.toHaveBeenCalled();
    expect(await screen.findByText(/gangguan.*jangan kirim ulang/i)).toBeInTheDocument();
  });
});
