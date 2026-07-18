import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

vi.mock("@/lib/api", () => ({
  api: {
    getInboxThreads: vi.fn(), getInboxThread: vi.fn(), replyInboxThread: vi.fn(),
    updateInboxThreadMode: vi.fn(), submitInboxFeedback: vi.fn(),
  },
  inboxManageLabel: vi.fn(), inboxAddNote: vi.fn(),
  inboxListNotes: vi.fn(), listCannedReplies: vi.fn(),
}));

import { api, inboxListNotes, listCannedReplies } from "@/lib/api";
import InboxPage from "./page";

const thread = (id, name) => ({
  id, mode: "manual", contact: { name, phone: `08${id}` }, labels: [],
  unread_count: 0, last_message_preview: name, last_message_at: null,
});
const detail = (id, name) => ({
  id, mode: "manual", contact: { name, phone: `08${id}` },
  channel: { display_name: "WhatsApp" }, messages: [],
});

describe("InboxPage request ordering", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    api.getInboxThreads.mockResolvedValue([thread(1, "Alpha"), thread(2, "Beta")]);
    api.replyInboxThread.mockResolvedValue({ message: "ok" });
    inboxListNotes.mockResolvedValue([]);
    listCannedReplies.mockResolvedValue([]);
  });

  it("does not let a completed reply refresh overwrite a newly selected thread", async () => {
    let resolveReply;
    const pendingReply = new Promise((resolve) => { resolveReply = resolve; });
    api.getInboxThread.mockImplementation((id) => Promise.resolve(detail(id, id === 1 ? "Alpha" : "Beta")));
    api.replyInboxThread.mockReturnValue(pendingReply);

    render(<InboxPage />);
    expect(await screen.findByText("WhatsApp / 081")).toBeInTheDocument();
    fireEvent.change(screen.getByPlaceholderText("Balas manual..."), {
      target: { value: "Balas Alpha" },
    });
    fireEvent.click(screen.getByRole("button", { name: "Kirim" }));

    const betaLabels = await screen.findAllByText("Beta");
    fireEvent.click(betaLabels[0].closest("button"));
    expect(await screen.findByText("WhatsApp / 082")).toBeInTheDocument();
    expect(screen.getByPlaceholderText("Balas manual...")).toHaveValue("");

    resolveReply({ message: "ok" });
    await waitFor(() => expect(api.replyInboxThread).toHaveBeenCalledWith(1, { text: "Balas Alpha" }));
    expect(screen.getByText("WhatsApp / 082")).toBeInTheDocument();
  });

  it("discards stale detail and notes, and replies only to the active thread", async () => {
    let resolveAlphaDetail;
    let resolveAlphaNotes;
    const alphaDetail = new Promise((resolve) => { resolveAlphaDetail = resolve; });
    const alphaNotes = new Promise((resolve) => { resolveAlphaNotes = resolve; });
    api.getInboxThread.mockImplementation((id) =>
      id === 1 ? alphaDetail : Promise.resolve(detail(2, "Beta"))
    );
    inboxListNotes.mockImplementation((id) =>
      id === 1
        ? alphaNotes
        : Promise.resolve([{ id: 2, content: "Catatan Beta", created_at: null }])
    );

    render(<InboxPage />);
    const betaLabels = await screen.findAllByText("Beta");
    const betaButton = betaLabels[0].closest("button");
    fireEvent.click(betaButton);
    expect(await screen.findByText("WhatsApp / 082")).toBeInTheDocument();
    await waitFor(() => expect(document.body).toHaveTextContent("Catatan Beta"));

    resolveAlphaDetail(detail(1, "Alpha"));
    resolveAlphaNotes([{ id: 1, content: "Catatan Alpha", created_at: null }]);
    await waitFor(() => expect(api.getInboxThread).toHaveBeenCalledWith(1));
    expect(screen.getByText("WhatsApp / 082")).toBeInTheDocument();
    expect(document.body).not.toHaveTextContent("Catatan Alpha");
    expect(document.body).toHaveTextContent("Catatan Beta");

    fireEvent.change(screen.getByPlaceholderText("Balas manual..."), {
      target: { value: "Balas ke Beta" },
    });
    fireEvent.click(screen.getByRole("button", { name: "Kirim" }));

    await waitFor(() => expect(api.replyInboxThread).toHaveBeenCalled());
    expect(api.replyInboxThread).toHaveBeenCalledWith(2, { text: "Balas ke Beta" });
  });
});
