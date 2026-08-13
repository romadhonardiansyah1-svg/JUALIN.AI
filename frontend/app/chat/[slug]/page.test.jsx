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

describe("PublicChatPage session id", () => {
  const STORAGE_KEY = "jualin_session_toko-uji";

  beforeEach(() => {
    vi.clearAllMocks();
    vi.spyOn(console, "error").mockImplementation(() => {});
    sessionStorage.clear();
    Element.prototype.scrollIntoView = vi.fn();
    api.getChatHistory.mockResolvedValue({ messages: [] });
    sendChatStream.mockReturnValue(vi.fn());
  });

  afterEach(() => vi.restoreAllMocks());

  it("mints the session id from Web Crypto, never Math.random", async () => {
    const randomSpy = vi.spyOn(Math, "random");

    render(<PublicChatPage />);

    await waitFor(() => expect(sessionStorage.getItem(STORAGE_KEY)).toBeTruthy());
    expect(sessionStorage.getItem(STORAGE_KEY)).toMatch(
      /^cust-(?:[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}|[0-9a-f]{32})$/
    );
    expect(randomSpy).not.toHaveBeenCalled();
  });

  it("refuses to mint a guessable id when Web Crypto is unavailable", async () => {
    const realCrypto = globalThis.crypto;
    Object.defineProperty(globalThis, "crypto", { value: undefined, configurable: true });
    try {
      render(<PublicChatPage />);
      expect(await screen.findByRole("alert")).toHaveTextContent(/tidak mendukung/i);
      expect(sessionStorage.getItem(STORAGE_KEY)).toBeNull();
    } finally {
      Object.defineProperty(globalThis, "crypto", { value: realCrypto, configurable: true });
    }
  });

  it("rewrites sessionStorage when the server hands back a different session id", async () => {
    sendChatStream.mockImplementation(({ onDone }) => {
      onDone({ full_response: "siap kak", session_id: "cust-server-assigned-id" });
      return vi.fn();
    });

    render(<PublicChatPage />);
    await waitFor(() => expect(sessionStorage.getItem(STORAGE_KEY)).toBeTruthy());
    const mintedId = sessionStorage.getItem(STORAGE_KEY);

    fireEvent.change(screen.getByPlaceholderText("Ketik pesan..."), {
      target: { value: "Saya mau beli" },
    });
    fireEvent.submit(screen.getByPlaceholderText("Ketik pesan...").closest("form"));

    await waitFor(() =>
      expect(sessionStorage.getItem(STORAGE_KEY)).toBe("cust-server-assigned-id")
    );
    expect(sessionStorage.getItem(STORAGE_KEY)).not.toBe(mintedId);
  });
});
