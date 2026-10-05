// Exercise the shipped browser module against a deliberately fallible DOM.
// No npm dependencies or frontend build step are required.
import test from "node:test";
import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";

const source = await readFile(new URL("../src/skilling_producer_example/static/app.js", import.meta.url), "utf8");
const { createUI } = await import(`data:text/javascript;base64,${Buffer.from(source).toString("base64")}`);

class Node {
  constructor(tag = "div") {
    this.tag = tag;
    this.children = [];
    this.dataset = {};
    this.listeners = {};
    this.isConnected = true;
    this.value = "";
    this.ownText = "";
  }
  set textContent(value) { this.ownText = value; this.children = []; }
  get textContent() { return this.ownText + this.children.map(node => node.textContent).join("\n"); }
  append(...nodes) {
    for (const node of nodes) this.children.push(...(node.tag === "fragment" ? node.children : [node]));
  }
  replaceChildren(...nodes) {
    if (this.fail) throw new Error("DOM render refused");
    this.ownText = "";
    this.children = [];
    this.append(...nodes);
  }
  addEventListener(name, listener) { this.listeners[name] = listener; }
}

function dom() {
  const nodes = new Map();
  return {
    getElementById(id) {
      if (!nodes.has(id)) nodes.set(id, new Node());
      return nodes.get(id);
    },
    createElement: tag => new Node(tag),
    createDocumentFragment: () => new Node("fragment"),
    querySelectorAll: () => [...nodes.values()].flatMap(node => node.children).filter(node => node.tag === "button"),
  };
}

function state(extra = {}) {
  return { csrf_token: "csrf", display_id: "display", snapshot: { course: "Welcome", position: "1.1", beat: { content: "Explain it" } }, controls: [], messages: [], objectives: [], homework: null, ...extra };
}

const feedback = { display_id: "feedback-display", question_number: 2, label: "B", correct: false, reason: "Try again <script>alert(1)</script>", offered: "Review this explanation", objectives: ["understand"] };

test("all canonical feedback reaches DOM before ack, with text escaping", async () => {
  const document = dom();
  const calls = [];
  let painted = false;
  const ui = createUI(document, async (path, options) => {
    calls.push(path);
    assert.equal(path, "/api/feedback/ack");
    assert.equal(painted, true);
    const actual = document.getElementById("feedback").textContent;
    for (const field of ["question number: 2", "label: B", "correct: false", feedback.reason, feedback.offered, "understand"]) assert.ok(actual.includes(field), field);
    assert.equal(document.getElementById("feedback").children.some(node => node.tag === "script"), false);
    assert.equal(options.headers["X-CSRF-Token"], "csrf");
    assert.deepEqual(JSON.parse(options.body), { display_id: "feedback-display" });
    return { ok: true, json: async () => state() };
  }, async () => { painted = true; });
  await ui.render(state({ feedback }));
  assert.deepEqual(calls, ["/api/feedback/ack"]);
  assert.ok(document.getElementById("feedback").textContent.includes(feedback.reason), "Acknowledged feedback remains readable until the next explicit course action");
});

for (const failedSection of ["feedback", "review", "controls"]) {
  test(`failed ${failedSection} render never acknowledges or settles`, async () => {
    const document = dom();
    document.getElementById(failedSection).fail = true;
    const calls = [];
    const ui = createUI(document, async path => { calls.push(path); throw new Error("must not send"); }, async () => {});
    await assert.rejects(ui.render(state({ feedback })), /DOM render refused/);
    assert.deepEqual(calls, []);
  });
}

test("navigation cancellation during paint leaves pending feedback untouched", async () => {
  const document = dom();
  const calls = [];
  let ui;
  ui = createUI(document, async path => { calls.push(path); }, async () => { ui.dispose(); });
  await ui.render(state({ feedback }));
  assert.deepEqual(calls, []);
});

test("a detached feedback element is never acknowledged", async () => {
  const document = dom();
  const calls = [];
  const ui = createUI(document, async path => { calls.push(path); }, async () => { document.getElementById("feedback").isConnected = false; });
  await ui.render(state({ feedback }));
  assert.deepEqual(calls, []);
});

test("a hidden browser never acknowledges canonical feedback", async () => {
  const document = dom();
  document.visibilityState = "hidden";
  const calls = [];
  const ui = createUI(document, async path => { calls.push(path); }, async () => {});
  await ui.render(state({ feedback }));
  assert.deepEqual(calls, []);
});

test("review displays every requirement before ack; submission needs a distinct click", async () => {
  const document = dom();
  const calls = [];
  const advice = [{ requirement_id: "one", advice: "Explain" }, { requirement_id: "two", advice: "Own words" }, { requirement_id: "three", advice: "Reflect" }];
  const ui = createUI(document, async path => {
    calls.push(path);
    assert.equal(path, "/api/review/ack");
    for (const item of advice) assert.ok(document.getElementById("review").textContent.includes(item.advice));
    assert.equal(document.getElementById("confirmations").children.length, 0);
    return { ok: true, json: async () => state() };
  }, async () => {});
  await ui.render(state({ review: { id: "review", kind: "homework", advice } }));
  assert.deepEqual(calls, ["/api/review/ack"]);
  assert.match(document.getElementById("confirmations").textContent, /submit homework/);
});

test("failed review ack exposes no confirmation or submission", async () => {
  const document = dom();
  const calls = [];
  const ui = createUI(document, async path => {
    calls.push(path);
    return { ok: false, status: 409, json: async () => ({ error: { message: "stale advice" } }) };
  }, async () => {});
  await assert.rejects(ui.render(state({ review: { id: "review", kind: "homework", advice: "Review" } })), /stale advice/);
  assert.deepEqual(calls, ["/api/review/ack"]);
  assert.equal(document.getElementById("confirmations").children.length, 0);
});

test("a prior confirmation cannot submit after a subsequent failed render", async () => {
  const document = dom();
  const calls = [];
  const ui = createUI(document, async path => {
    calls.push(path);
    return { ok: true, json: async () => state() };
  }, async () => {});
  await ui.render(state({ review: { id: "review", kind: "homework", advice: "All requirements" } }));
  const priorConfirm = document.getElementById("confirmations").children[0].listeners.click;
  document.getElementById("feedback").fail = true;
  await assert.rejects(ui.render(state({ feedback })), /DOM render refused/);
  await priorConfirm();
  assert.deepEqual(calls, ["/api/review/ack"]);
});

test("saved note sends exact UTF-8 text; typing invalidates separate confirmations", async () => {
  const document = dom();
  const calls = [];
  const exact = "# Goal note\nGoal: understand café ☕\nTakeaway: explain first\nNext action: try again\n";
  const review = { id: "review", kind: "objectives", objective_ids: ["explain"], advice: "Supported" };
  const ui = createUI(document, async (path, options) => {
    calls.push(path);
    if (path === "/api/note/save") assert.deepEqual(JSON.parse(options.body), { text: exact });
    return { ok: true, json: async () => state(path === "/api/state" ? { review } : {}) };
  }, async () => {});
  await ui.start();
  assert.match(document.getElementById("confirmations").textContent, /confirm explain/);
  document.getElementById("note").value = exact;
  document.getElementById("note").listeners.input();
  assert.equal(document.getElementById("confirmations").children.length, 0);
  await document.getElementById("note-form").listeners.submit({ preventDefault() {} });
  assert.deepEqual(calls, ["/api/state", "/api/review/ack", "/api/note/save"]);
});

test("chat/course strings are text and chat alone never submits course actions", async () => {
  const document = dom();
  const calls = [];
  const malicious = "<img src=x onerror=alert(1)>";
  const ui = createUI(document, async path => { calls.push(path); }, async () => {});
  await ui.render(state({ messages: [{ role: "assistant", content: malicious }], snapshot: { beat: { content: malicious } } }));
  assert.ok(document.getElementById("messages").textContent.includes(malicious));
  assert.ok(document.getElementById("beat").textContent.includes(malicious));
  assert.deepEqual(calls, []);
});

test("learner flow shows authored content and complete advice without controller metadata", async () => {
  const document = dom();
  const ui = createUI(document, async () => ({ ok: true, json: async () => state() }), async () => {});
  await ui.render(state({
    snapshot: { beat: { name: "quiz", title: "Try explaining", body: "A familiar situation", number: 1, text: "What happens?", options: [{ label: "A", text: "An example" }], revision: "hidden-beat-revision" } },
    objectives: [{ id: "explain", text: "Explain in your own words", verify: "Use a real example", settleable_now: true }],
    homework: { revision: "hidden-slot-revision", active: { title: "Try the method", requirements: [{ text: "Explain a topic" }, { text: "Ask for a change" }, { text: "Reflect in the note" }] } },
    note: { path: "showcase/welcome-skilling/goal.md", digest: "hidden-note-digest" },
    review: { id: "review", kind: "homework", note_digest: "hidden-note-digest", advice: { revision: "hidden-review-revision", evidence_digest: "hidden-evidence-digest", requirements: [{ id: "1.2/required/1", verdict: "supported", reason: "A clear explanation" }, { id: "1.2/required/2", verdict: "partial", reason: "Give a specific change" }, { id: "1.2/required/3", verdict: "not-yet", reason: "Add your reflection" }], stretch_goals: [] } },
    refresh: ["objective-evidence", "homework-evidence"],
  }));
  const teaching = document.getElementById("beat").textContent;
  for (const expected of ["Try explaining", "A familiar situation", "What happens?", "A) An example"]) assert.ok(teaching.includes(expected));
  const advice = document.getElementById("review").textContent;
  for (const expected of ["Explain a topic", "Ask for a change", "Reflect in the note", "A clear explanation", "Give a specific change", "Add your reflection", "not yet"]) assert.ok(advice.includes(expected));
  const all = ["beat", "review", "objectives", "homework", "note-inspection"].map(id => document.getElementById(id).textContent).join("\n");
  assert.equal(all.includes("hidden-"), false);
  assert.equal(all.includes("settleable"), false);
  assert.match(document.getElementById("refresh-hints").textContent, /own explanation/);
  assert.match(document.getElementById("refresh-hints").textContent, /each homework requirement/);
});
