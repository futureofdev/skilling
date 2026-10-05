import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, expect, it, vi } from "vitest";
import { DemoIdentity } from "./DemoIdentity";

vi.mock("./App", () => ({ App: () => <div>Authenticated tutor</div> }));
afterEach(() => vi.unstubAllGlobals());

it("waits for a configured learner and switches through a same-origin JSON request", async () => {
  const fetcher = vi.fn(async (url: string, init?: RequestInit) => {
    if (url === "/api/demo") return new Response(JSON.stringify({
      enabled: true, selected: null, label: "Local demo identity — not production authentication",
      choices: [{ selector: "alice", label: "Alice" }, { selector: "bob", label: "Bob" }],
    }));
    expect(init?.credentials).toBe("same-origin");
    expect(init?.headers).toEqual({ "Content-Type": "application/json" });
    expect(JSON.parse(String(init?.body))).toEqual({ selector: "alice" });
    return new Response(JSON.stringify({ selected: "Alice" }));
  });
  vi.stubGlobal("fetch", fetcher);
  render(<DemoIdentity />);
  const selector = await screen.findByRole("combobox", { name: "Demo learner" });
  expect(screen.queryByText("Authenticated tutor")).toBeNull();
  fireEvent.change(selector, { target: { value: "alice" } });
  await waitFor(() => expect(screen.getByText("Authenticated tutor")).toBeInTheDocument());
  expect(selector).toHaveValue("alice");
});

it("uses the application identity when demo selection is disabled", async () => {
  vi.stubGlobal("fetch", vi.fn(async () => new Response(JSON.stringify({ enabled: false }))));
  render(<DemoIdentity />);
  expect(await screen.findByText("Authenticated tutor")).toBeInTheDocument();
  expect(screen.queryByRole("combobox")).toBeNull();
});
