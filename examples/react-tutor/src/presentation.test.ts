import { afterEach, describe, expect, it, vi } from "vitest";
import { afterVisiblePaint } from "./presentation";

afterEach(() => {
  vi.restoreAllMocks();
  vi.unstubAllGlobals();
  document.body.innerHTML = "";
});

describe("presentation receipts", () => {
  function frames() {
    const queue = new Map<number, FrameRequestCallback>();
    let count = 0;
    vi.stubGlobal("requestAnimationFrame", (callback: FrameRequestCallback) => {
      queue.set(++count, callback);
      return count;
    });
    vi.stubGlobal("cancelAnimationFrame", (id: number) => queue.delete(id));
    return () => {
      const entries = [...queue.entries()];
      queue.clear();
      entries.forEach(([, callback]) => callback(0));
    };
  }
  it("waits for a committed, visible display and two animation frames", () => {
    const paint = frames();
    const node = document.createElement("article");
    document.body.append(node);
    const acknowledge = vi.fn();
    const cancel = afterVisiblePaint(node, acknowledge);
    paint();
    expect(acknowledge).not.toHaveBeenCalled();
    paint();
    expect(acknowledge).toHaveBeenCalledOnce();
    cancel();
  });
  it("never acknowledges an unmounted or superseded display", () => {
    const paint = frames();
    const node = document.createElement("article");
    document.body.append(node);
    const acknowledge = vi.fn();
    const cancel = afterVisiblePaint(node, acknowledge);
    paint();
    cancel();
    node.remove();
    paint();
    expect(acknowledge).not.toHaveBeenCalled();
  });
  it("waits for the tab to become visible", () => {
    const paint = frames();
    const visible = vi
      .spyOn(document, "visibilityState", "get")
      .mockReturnValue("hidden");
    const node = document.createElement("article");
    document.body.append(node);
    const acknowledge = vi.fn();
    const cancel = afterVisiblePaint(node, acknowledge);
    paint();
    paint();
    expect(acknowledge).not.toHaveBeenCalled();
    visible.mockReturnValue("visible");
    document.dispatchEvent(new Event("visibilitychange"));
    paint();
    paint();
    expect(acknowledge).toHaveBeenCalledOnce();
    cancel();
  });
  it("keeps a hidden context panel unacknowledged until it is opened", async () => {
    const paint = frames();
    const panel = document.createElement("aside");
    panel.hidden = true;
    const node = document.createElement("article");
    panel.append(node);
    document.body.append(panel);
    const acknowledge = vi.fn();
    const cancel = afterVisiblePaint(node, acknowledge);
    paint();
    paint();
    expect(acknowledge).not.toHaveBeenCalled();
    panel.hidden = false;
    await Promise.resolve();
    paint();
    paint();
    expect(acknowledge).toHaveBeenCalledOnce();
    panel.hidden = true;
    panel.hidden = false;
    await Promise.resolve();
    paint();
    paint();
    expect(acknowledge).toHaveBeenCalledOnce();
    cancel();
  });
  it("waits until the current response enters the scroll viewport", () => {
    const paint = frames();
    let observeVisibility: ((visible: boolean) => void) | undefined;
    vi.stubGlobal("IntersectionObserver", class {
      constructor(private callback: IntersectionObserverCallback) {}
      observe(target: Element) {
        observeVisibility = (isIntersecting) => this.callback(
          [{ target, isIntersecting } as IntersectionObserverEntry],
          this as unknown as IntersectionObserver,
        );
      }
      disconnect() {}
    });
    const node = document.createElement("article");
    document.body.append(node);
    const acknowledge = vi.fn();
    const cancel = afterVisiblePaint(node, acknowledge);
    paint();
    paint();
    expect(acknowledge).not.toHaveBeenCalled();
    observeVisibility?.(true);
    paint();
    paint();
    expect(acknowledge).toHaveBeenCalledOnce();
    cancel();
  });
});
