// A receipt needs visible content, then two animation frames. A hidden context
// panel or content below the chat viewport must not acknowledge presentation.
export function afterVisiblePaint(
  element: HTMLElement,
  callback: () => void,
): () => void {
  let frame = 0;
  let cancelled = false;
  let completed = false;
  let inViewport = typeof IntersectionObserver === "undefined";
  const visible = () =>
    !cancelled &&
    !completed &&
    inViewport &&
    element.isConnected &&
    document.visibilityState !== "hidden" &&
    !element.closest('[hidden], [inert], [aria-hidden="true"], details:not([open])');
  const schedule = () => {
    cancelAnimationFrame(frame);
    if (!visible()) return;
    frame = requestAnimationFrame(() => {
      frame = requestAnimationFrame(() => {
        if (visible()) {
          completed = true;
          callback();
        }
      });
    });
  };
  const intersection = typeof IntersectionObserver === "undefined" ? null :
    new IntersectionObserver((entries) => {
      inViewport = entries.some((entry) => entry.target === element && entry.isIntersecting);
      schedule();
    });
  intersection?.observe(element);
  const visibility = new MutationObserver(schedule);
  for (let ancestor: HTMLElement | null = element; ancestor; ancestor = ancestor.parentElement) {
    visibility.observe(ancestor, {
      attributes: true,
      attributeFilter: ["hidden", "inert", "aria-hidden", "open"],
    });
  }
  document.addEventListener("visibilitychange", schedule);
  schedule();
  return () => {
    cancelled = true;
    cancelAnimationFrame(frame);
    intersection?.disconnect();
    visibility.disconnect();
    document.removeEventListener("visibilitychange", schedule);
  };
}
