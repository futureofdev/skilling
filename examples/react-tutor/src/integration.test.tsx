import {
  act,
  fireEvent,
  render,
  screen,
  waitFor,
} from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { App } from "./App";
import type { TutorState } from "./types";

vi.setConfig({ testTimeout: 30000 });

type Wire = {
  request_id: string;
  display_id?: string;
  message?: string;
  trigger: string;
  messages: object[];
};
function state(
  display_id: string,
  messages: TutorState["messages"] = [],
): TutorState {
  return {
    display_id,
    snapshot: {
      course: { id: "welcome", title: "Learning together", version: "1.0" },
      position: { phase: 1, lesson: 1, beat: "gate-concept" },
      revision: "revision",
      beat: { name: "gate-concept", body: "The authored concept." },
      completed_count: 0,
      lesson_count: 3,
      legal_inputs: ["proceed"],
    },
    controls: [],
    feedback: null,
    messages,
    continuation: null,
    history_notice: "Saved progress.",
  };
}
function sse(parts: object[]): Response {
  return new Response(
    parts.map((part) => `data: ${JSON.stringify(part)}\n\n`).join("") +
      "data: [DONE]\n\n",
    {
      headers: {
        "content-type": "text/event-stream",
        "x-vercel-ai-ui-message-stream": "v1",
      },
    },
  );
}
function completed(next: TutorState): object[] {
  return [
    { type: "start", messageId: "reply" },
    { type: "text-start", id: "text" },
    { type: "text-delta", id: "text", delta: "Accepted reply." },
    { type: "text-end", id: "text" },
    { type: "data-skilling", data: { type: "state", state: next } },
    { type: "finish", finishReason: "stop" },
  ];
}
beforeEach(() => {
  vi.spyOn(document, "visibilityState", "get").mockReturnValue("visible");
  vi.stubGlobal("requestAnimationFrame", (callback: FrameRequestCallback) =>
    window.setTimeout(() => callback(0), 0),
  );
  vi.stubGlobal("cancelAnimationFrame", (id: number) =>
    window.clearTimeout(id),
  );
});
afterEach(() => {
  vi.unstubAllGlobals();
  vi.restoreAllMocks();
});
async function ready() {
  await waitFor(() => expect(screen.getByLabelText("Make room for a question.")).not.toBeDisabled(), { timeout: 15000 });
  fireEvent.change(await screen.findByLabelText("Make room for a question."), {
    target: { value: "draft" },
  });
  await waitFor(
    () =>
      expect(
        screen.getByRole("button", { name: "Send message" }),
      ).not.toBeDisabled(),
    { timeout: 15000 },
  );
}
function send(text: string) {
  fireEvent.change(screen.getByLabelText("Make room for a question."), {
    target: { value: text },
  });
  fireEvent.click(screen.getByRole("button", { name: "Send message" }));
}

describe("real AI SDK transport and accepted presentation", () => {
  it("sends bounded latest input and retries the exact failed request without acknowledging failed output", async () => {
    let current = state("initial", [
      { role: "learner", text: "Earlier context ".repeat(20) },
    ]);
    const requests: Wire[] = [];
    const acknowledgements: string[] = [];
    vi.stubGlobal(
      "fetch",
      vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
        const path = String(input);
        if (path === "/api/work") return Response.json({ text: "" });
        if (path.endsWith("/state")) return Response.json(current);
        const body = JSON.parse(String(init?.body));
        if (path.endsWith("/ack")) {
          acknowledgements.push(body.display_id);
          current = { ...current, display_id: `ack-${body.display_id}` };
          return Response.json(current);
        }
        if (path.endsWith("/chat")) {
          requests.push(body);
          if (requests.length === 1) {
            current = state("saved-after-error", [
              { role: "learner", text: "continue" },
            ]);
            return sse([
              { type: "start", messageId: "failed" },
              {
                type: "data-skilling",
                data: {
                  type: "error",
                  code: "model-unavailable",
                  message: "Please retry.",
                  state: current,
                },
              },
              { type: "error", errorText: "Please retry." },
              { type: "finish", finishReason: "error" },
            ]);
          }
          current = state("accepted", [
            { role: "learner", text: "continue" },
            { role: "tutor", text: "Accepted reply." },
          ]);
          return sse(completed(current));
        }
        throw new Error(`Unexpected request: ${path}`);
      }),
    );
    render(<App />);
    await ready();
    send("continue");
    await waitFor(() =>
      expect(screen.getByRole("alert")).toHaveTextContent("Please retry."),
    );
    expect(acknowledgements).toEqual(["initial"]);
    expect(JSON.stringify(requests[0]).length).toBeLessThan(1000);
    expect(JSON.stringify(requests[0])).not.toContain("Earlier context");
    expect(requests[0].display_id).toBe("ack-initial");
    fireEvent.click(screen.getByRole("button", { name: "Retry last turn" }));
    await waitFor(() =>
      expect(screen.getByText("Accepted reply.")).toBeVisible(),
    );
    await ready();
    expect(requests).toHaveLength(2);
    expect(requests[1].request_id).toBe(requests[0].request_id);
    expect(requests[1].display_id).toBe(requests[0].display_id);
    expect(requests[1].trigger).toBe("submit-message");
    expect(requests[1].message).toBe(requests[0].message);
    expect(acknowledgements).toEqual(["initial", "accepted"]);
  });

  it("shows each delta before completion, discards rejected drafts, and acknowledges only final state", async () => {
    let current = state("initial");
    const acknowledgements: string[] = [];
    let output: ReadableStreamDefaultController<Uint8Array> | undefined;
    const encode = (part: object) =>
      new TextEncoder().encode(`data: ${JSON.stringify(part)}\n\n`);
    vi.stubGlobal(
      "fetch",
      vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
        const path = String(input);
        if (path === "/api/work") return Response.json({ text: "" });
        if (path.endsWith("/state")) return Response.json(current);
        if (path.endsWith("/ack")) {
          const body = JSON.parse(String(init?.body));
          acknowledgements.push(body.display_id);
          current = { ...current, display_id: `ack-${body.display_id}` };
          return Response.json(current);
        }
        if (path.endsWith("/chat"))
          return new Response(
            new ReadableStream({
              start(controller) {
                output = controller;
              },
            }),
            {
              headers: {
                "content-type": "text/event-stream",
                "x-vercel-ai-ui-message-stream": "v1",
              },
            },
          );
        throw new Error(`Unexpected request: ${path}`);
      }),
    );
    render(<App />);
    await ready();
    const panel = screen.getByLabelText("Course context and your notes");
    expect(panel).not.toBeVisible();
    fireEvent.click(screen.getByRole("button", { name: "Course & notes" }));
    expect(panel).toBeVisible();
    fireEvent.click(screen.getByText("Your practice & reflection"));
    const note = screen.getByLabelText("Your learning note");
    await waitFor(() => expect(note).not.toBeDisabled());
    fireEvent.change(note, { target: { value: "My unsaved reflection" } });
    fireEvent.click(screen.getByRole("button", { name: "Close course context" }));
    expect(panel).not.toBeVisible();
    expect(screen.getByRole("button", { name: "Course & notes" })).toHaveFocus();
    fireEvent.click(screen.getByRole("button", { name: "Course & notes" }));
    expect(note).toHaveValue("My unsaved reflection");
    fireEvent.keyDown(document, { key: "Escape" });
    expect(panel).not.toBeVisible();
    send("Explain");
    await waitFor(() => expect(output).toBeDefined());
    await act(async () => {
      for (const part of [
        { type: "start", messageId: "drafts" },
        { type: "text-start", id: "a" },
        { type: "text-delta", id: "a", delta: "Rejected draft one." },
        { type: "text-end", id: "a" },
        { type: "data-skilling", data: { type: "text-reset" } },
        { type: "text-start", id: "b" },
        { type: "text-delta", id: "b", delta: "Rejected draft two." },
        { type: "text-end", id: "b" },
        { type: "data-skilling", data: { type: "text-reset" } },
        { type: "text-start", id: "c" },
        { type: "text-delta", id: "c", delta: "Accepted " },
      ])
        output?.enqueue(encode(part));
    });
    await waitFor(() => expect(screen.getByText("Accepted")).toBeVisible());
    expect(screen.queryByText("Accepted reply.")).toBeNull();
    expect(acknowledgements).toEqual(["initial"]);
    await act(async () => {
      output?.enqueue(encode({ type: "text-delta", id: "c", delta: "reply." }));
    });
    await waitFor(() => expect(screen.getByText("Accepted reply.")).toBeVisible());
    expect(acknowledgements).toEqual(["initial"]);
    expect(screen.queryByText("Rejected draft one.")).toBeNull();
    expect(screen.queryByText("Rejected draft two.")).toBeNull();
    await act(async () => {
      current = state("accepted", [
        { role: "learner", text: "Explain" },
        { role: "tutor", text: "Accepted reply." },
      ]);
      output?.enqueue(encode({ type: "text-end", id: "c" }));
      output?.enqueue(
        encode({
          type: "data-skilling",
          data: { type: "state", state: current },
        }),
      );
      output?.enqueue(encode({ type: "finish", finishReason: "stop" }));
      output?.enqueue(new TextEncoder().encode("data: [DONE]\n\n"));
      output?.close();
    });
    await ready();
    expect(acknowledgements).toEqual(["initial", "accepted"]);
  });
  it("opens and focuses authored lesson reference from its chat button", async () => {
    const current = state("initial");
    vi.stubGlobal("fetch", vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
      const path = String(input);
      if (path === "/api/work") return Response.json({ text: "" });
      if (path.endsWith("/state")) return Response.json(current);
      if (path.endsWith("/ack")) {
        const body = JSON.parse(String(init?.body));
        return Response.json({ ...current, display_id: `ack-${body.display_id}` });
      }
      throw new Error(`Unexpected request: ${path}`);
    }));
    render(<App />);
    const reference = await screen.findByRole("button", { name: "Lesson reference" });
    const panel = screen.getByLabelText("Course context and your notes");
    expect(panel).not.toBeVisible();
    fireEvent.click(reference);
    await waitFor(() => expect(panel).toBeVisible());
    const authored = screen.getByText("The authored concept.");
    await waitFor(() => expect(authored).toBeVisible());
    const details = authored.closest("details");
    expect(details).toHaveAttribute("open");
    await waitFor(() => expect(details?.contains(document.activeElement)).toBe(true));
  });

  it("offers a useful empty-gate reference without sending a message for the learner", async () => {
    const current = state("initial");
    current.snapshot.beat = { name: "gate-concept" };
    const fetcher = vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
      const path = String(input);
      if (path === "/api/work") return Response.json({ text: "" });
      if (path.endsWith("/state")) return Response.json(current);
      if (path.endsWith("/ack")) {
        const body = JSON.parse(String(init?.body));
        return Response.json({ ...current, display_id: `ack-${body.display_id}` });
      }
      throw new Error(`Unexpected request: ${path}`);
    });
    vi.stubGlobal("fetch", fetcher);
    render(<App />);
    fireEvent.click(await screen.findByRole("button", { name: "Lesson reference" }));
    const recap = await screen.findByRole("button", { name: "Ask for a lesson recap" });
    expect(recap).toBeVisible();
    expect(screen.getByText(/there’s no separate lesson text/)).toBeVisible();
    fireEvent.click(recap);
    const composer = screen.getByLabelText("Make room for a question.");
    expect(composer).toHaveValue("Could you recap the current lesson and its key ideas?");
    await waitFor(() => expect(composer).toHaveFocus());
    expect(screen.getByLabelText("Course context and your notes")).not.toBeVisible();
    expect(fetcher.mock.calls.some(([input]) => String(input).endsWith("/chat"))).toBe(false);
  });

});
