// Course and model strings are always text, never markup or executable URLs.
export function createUI(document, fetcher, paint = () => new Promise(resolve => requestAnimationFrame(() => requestAnimationFrame(resolve)))) {
  let state = null;
  let generation = 0;
  let busy = false;
  let alive = true;
  let noteDirty = false;
  let presentationValid = false;
  let lastFeedback = null;
  const acknowledgedReviews = new Set();
  const el = id => document.getElementById(id);

  function text(tag, value, className = "") {
    const node = document.createElement(tag);
    node.textContent = value == null ? "" : String(value);
    if (className) node.className = className;
    return node;
  }

  // Keep authored requirement identities and full advice visible, even when the
  // provider's prose spans several fields. No content is interpreted as HTML.
  function content(parent, value, label = "") {
    if (value == null) return;
    if (Array.isArray(value)) {
      for (const item of value) content(parent, item);
    } else if (typeof value === "object") {
      if (label) parent.append(text("h4", label.replaceAll("_", " ")));
      for (const [key, item] of Object.entries(value)) content(parent, item, key);
    } else {
      parent.append(text("p", `${label ? label.replaceAll("_", " ") + ": " : ""}${value}`, "content"));
    }
  }

  function teaching(parent, beat) {
    if (!beat) return;
    if (beat.title) parent.append(text("h3", beat.title));
    content(parent, beat.body || beat.content);
    if (beat.key_terms) {
      parent.append(text("h4", "Key terms"));
      content(parent, beat.key_terms);
    }
    if (beat.objectives?.length) {
      parent.append(text("h4", "What you will learn"));
      content(parent, beat.objectives);
    }
    if (beat.objective) content(parent, beat.objective);
    const question = beat.question || beat;
    if (question.text) {
      parent.append(text("h3", question.number ? `Question ${question.number}` : "Your question"));
      content(parent, question.text);
      for (const option of question.options || []) content(parent, `${option.label}) ${option.text}`);
    }
    if (beat.offer_revisit) content(parent, "Ask your tutor to revisit this idea before you continue.");
  }

  function assignment(parent, work) {
    if (!work) return;
    if (work.title) parent.append(text("h4", work.title));
    content(parent, work.objective);
    for (const [index, item] of (work.requirements || []).entries()) content(parent, `${index + 1}. ${item.text}`);
    if (work.stretch_goals?.length) {
      parent.append(text("h4", "Optional stretch goals"));
      for (const item of work.stretch_goals) content(parent, item.text);
    }
    content(parent, work.submission);
  }

  function advice(parent, next) {
    const value = next.review.advice;
    const groups = typeof value === "string" ? [["Advice", [{ reason: value }]]] : Array.isArray(value) ? [["Requirements", value]] : [
      ["Objectives", value?.objectives || []], ["Requirements", value?.requirements || []], ["Optional stretch goals", value?.stretch_goals || []],
    ];
    for (const [name, items] of groups) {
      if (!items.length) continue;
      parent.append(text("h4", name));
      for (const item of items) {
        const id = item.id || item.requirement_id;
        const objective = next.objectives?.find(objective => objective.id === id);
        const index = id && Number(id.split("/").at(-1)) - 1;
        const authored = name === "Objectives" ? objective?.text : (name === "Optional stretch goals" ? next.homework?.active?.stretch_goals : next.homework?.active?.requirements)?.[index]?.text;
        if (id) content(parent, authored ? `${id}: ${authored}` : id);
        if (item.verdict) content(parent, `Judgement: ${item.verdict.replaceAll("-", " ")}`);
        content(parent, item.reason || item.advice);
      }
    }
  }

  function status(message, error = false) {
    el("status").textContent = message;
    el("status").dataset.error = String(error);
  }

  function resultStatus(result, fallback) {
    const error = result.note_error || result.startup_error || result.tutor_error;
    status(error || fallback, Boolean(error));
  }

  function lock(value) {
    busy = value;
    for (const button of document.querySelectorAll("button")) button.disabled = value || (!presentationValid && button.id !== "refresh" && !button.dataset.demo);
  }

  async function request(path, body) {
    const response = await fetcher(path, {
      method: body === undefined ? "GET" : "POST",
      credentials: "same-origin",
      headers: body === undefined ? {} : { "Content-Type": "application/json", "X-CSRF-Token": state.csrf_token },
      ...(body === undefined ? {} : { body: JSON.stringify(body) }),
    });
    const result = await response.json();
    if (!response.ok) throw new Error(result.error?.message || `Request failed (${response.status})`);
    return result;
  }

  function button(label, action) {
    const node = text("button", label);
    node.type = "button";
    node.addEventListener("click", action);
    return node;
  }

  async function selectDemo(selector, course_id) {
    if (busy || !alive) return;
    lock(true);
    generation++;
    presentationValid = false;
    acknowledgedReviews.clear();
    lastFeedback = null;
    noteDirty = false;
    for (const id of ["note", "message", "objective-evidence", "homework-evidence", "artifact-title"]) el(id).value = "";
    for (const id of ["messages", "beat", "feedback", "review", "confirmations"]) el(id).replaceChildren();
    try {
      const result = await request("/api/demo/select", { selector, course_id });
      await render(result);
      resultStatus(result, "Local demo learner selected. Conversation starts fresh.");
    } catch (error) {
      status(`${error.message} Refresh before continuing.`, true);
    } finally {
      if (alive) lock(false);
    }
  }

  async function mutate(path, body) {
    if (busy || !alive || !presentationValid) return false;
    if (path === "/api/review/confirm" && (noteDirty || !acknowledgedReviews.has(body.review_id))) return false;
    lock(true);
    try {
      const result = await request(path, body);
      if (path.startsWith("/api/actions/")) lastFeedback = null;
      await render(result);
      resultStatus(result, "Workspace updated.");
      return true;
    } catch (error) {
      presentationValid = false;
      el("confirmations").replaceChildren();
      status(`${error.message} Refresh the workspace before trying again.`, true);
      return false;
    } finally {
      if (alive) lock(false);
    }
  }

  function canonicalFeedback(feedback) {
    const fragment = document.createDocumentFragment();
    fragment.append(text("h3", "Quiz feedback"));
    for (const key of ["question_number", "label", "correct", "reason", "offered", "objectives"]) {
      content(fragment, feedback[key], key);
    }
    return fragment;
  }

  function confirmations(review) {
    const target = el("confirmations");
    target.replaceChildren();
    if (!review || noteDirty || !acknowledgedReviews.has(review.id)) return;
    if (review.kind === "homework") {
      target.append(button("I reviewed each requirement — submit homework", () => mutate("/api/review/confirm", { review_id: review.id })));
    } else {
      const objectives = review.objective_ids || review.objectives || state.objectives || [];
      for (const objective of objectives) {
        const id = typeof objective === "string" ? objective : objective.id || objective.objective_id;
        if (!id) continue;
        target.append(button(`I authored this work and confirm ${id}`, () => mutate("/api/review/confirm", { review_id: review.id, objective_id: id })));
      }
    }
  }

  function rendered(current) {
    return alive && generation === current && document.visibilityState !== "hidden" &&
      ["messages", "beat", "feedback", "review"].every(id => el(id).isConnected);
  }

  async function render(next) {
    if (!alive) return;
    const current = ++generation;
    presentationValid = false;
    el("confirmations").replaceChildren();
    // Construct both presentation fragments before any acknowledgement. If a
    // DOM operation fails, pending feedback/review stays unacknowledged.
    if (next.feedback) lastFeedback = next.feedback;
    const feedback = lastFeedback ? canonicalFeedback(lastFeedback) : document.createDocumentFragment();
    const review = document.createDocumentFragment();
    if (next.review) {
      review.append(text("h3", "Informal tutor advice — review before confirming"));
      advice(review, next);
      if (next.review.note_digest) content(review, "Advice includes your inspected saved note. If you edit it, save and request fresh advice before confirming.");
    }
    const beat = document.createDocumentFragment();
    teaching(beat, next.snapshot?.beat);
    el("beat").replaceChildren(beat);
    el("feedback").replaceChildren(feedback);
    el("review").replaceChildren(review);
    state = next;
    el("demo").hidden = !next.demo;
    el("demo-label").textContent = next.demo?.label || "";
    el("demo-selected").textContent = next.demo?.selected ? `Selected: ${next.demo.selected}` : "Select a configured demonstration learner.";
    const choices = document.createDocumentFragment();
    for (const choice of next.demo?.choices || []) {
      for (const course of choice.courses) {
        const node = button(`${choice.label} · ${course}`, () => selectDemo(choice.selector, course));
        node.dataset.demo = "true";
        choices.append(node);
      }
    }
    el("demo-choices").replaceChildren(choices);
    el("history-notice").textContent = next.history_notice || "Conversation is temporary. After restart, course progress remains; explain any work whose conversation evidence was lost.";
    const course = next.snapshot?.course;
    const position = next.snapshot?.position;
    const courseTitle = typeof course === "object" ? course?.title : course;
    const coordinate = typeof position === "object" ? `${position?.phase}.${position?.lesson}` : position;
    el("progress").textContent = `${courseTitle || "Welcome"} · ${coordinate || ""}`;
    const objectiveNodes = document.createDocumentFragment();
    for (const objective of next.objectives || []) {
      content(objectiveNodes, objective.text);
      if (objective.verify) content(objectiveNodes, `How to check your work: ${objective.verify}`);
    }
    el("objectives").replaceChildren(objectiveNodes);
    const homeworkNodes = document.createDocumentFragment();
    assignment(homeworkNodes, next.homework?.active);
    el("homework").replaceChildren(homeworkNodes);
    el("homework-review-form").hidden = !next.homework?.active;
    const archiveNodes = document.createDocumentFragment();
    if (next.archive) {
      archiveNodes.append(text("h3", "Homework submitted"));
      archiveNodes.append(text("p", "Your submission is archived. Tutor advice is informal; archived null verdicts do not represent a score or certification."));
      assignment(archiveNodes, next.archive);
    }
    el("archive").replaceChildren(archiveNodes);
    if (!noteDirty && next.note?.text !== undefined) el("note").value = next.note.text;
    el("note-inspection").textContent = next.note ? `Saved file: ${next.note.path || "showcase/welcome-skilling/goal.md"}. Changes require saving and fresh advice.` : "No note has been saved yet.";
    const refreshHints = {
      "objective-evidence": "Supply your own explanation in Review your learning, then ask for fresh advice.",
      "homework-evidence": "Update and save your note with your reflection, then supply real evidence for each homework requirement and review it.",
      teaching: "Refresh the workspace, then ask your tutor to explain again.",
      progress: "Refresh the workspace to see current progress, then ask your tutor again.",
    };
    const hints = (next.refresh || []).map(hint => refreshHints[hint]).filter(Boolean);
    el("refresh-hints").textContent = hints.join("\n");
    const messages = document.createDocumentFragment();
    for (const message of next.messages || []) {
      const node = text("p", `${message.role || "Tutor"}: ${message.content ?? message.text ?? ""}`, "message");
      node.dataset.role = message.role || "assistant";
      messages.append(node);
    }
    el("messages").replaceChildren(messages);
    el("controls").replaceChildren();
    el("artifact-form").hidden = !next.artifact_available;
    // One actual paint opportunity, then check that this exact presentation is
    // still attached. Navigating away or a newer render cancels the ack.
    await paint();
    if (!rendered(current)) return;
    if (next.feedback) {
      const result = await request("/api/feedback/ack", { display_id: next.feedback.display_id || next.display_id });
      if (rendered(current)) await render(result);
      return;
    }
    if (next.review && !noteDirty && !acknowledgedReviews.has(next.review.id)) {
      await request("/api/review/ack", { review_id: next.review.id });
      if (!rendered(current)) return;
      acknowledgedReviews.add(next.review.id);
    }
    if (next.continuation) {
      const result = await request("/api/continue", { continuation_id: next.continuation.id });
      if (rendered(current)) await render(result);
      return;
    }
    presentationValid = true;
    confirmations(next.review);
  }

  function bind() {
    el("note").addEventListener("input", () => {
      noteDirty = true;
      acknowledgedReviews.clear();
      el("confirmations").replaceChildren();
      status("Unsaved changes. Save, inspect and request fresh advice before confirming.");
    });
    el("chat-form").addEventListener("submit", event => {
      event.preventDefault();
      const message = el("message").value;
      if (!message.trim()) return;
      el("message").value = "";
      acknowledgedReviews.clear();
      mutate("/api/chat", { message, display_id: state.display_id });
    });
    el("note-form").addEventListener("submit", async event => {
      event.preventDefault();
      acknowledgedReviews.clear();
      const saved = await mutate("/api/note/save", { text: el("note").value });
      if (saved) noteDirty = false;
    });
    for (const [form, kind, evidence] of [["objective-review-form", "objectives", "objective-evidence"], ["homework-review-form", "homework", "homework-evidence"]]) {
      el(form).addEventListener("submit", event => {
        event.preventDefault();
        if (noteDirty) { status("Save your edited note before requesting advice.", true); return; }
        mutate(`/api/review/${kind}`, { evidence: el(evidence).value });
      });
    }
    el("artifact-form").addEventListener("submit", event => {
      event.preventDefault();
      mutate("/api/artifact", { title: el("artifact-title").value });
    });
    el("artifact-decline").addEventListener("click", () => {
      el("artifact-form").hidden = true;
      status("Artifact offer declined. Your progress is unchanged.");
    });
    el("refresh").addEventListener("click", async () => {
      if (busy || !alive) return;
      lock(true);
      acknowledgedReviews.clear();
      try {
        const result = await request("/api/state");
        await render(result);
        resultStatus(result, "Workspace refreshed. Unsaved note text is preserved.");
      } catch (error) {
        status(error.message, true);
      } finally {
        if (alive) lock(false);
      }
    });
  }

  async function start() {
    bind();
    lock(true);
    try {
      const result = await request("/api/state");
      await render(result);
      resultStatus(result, "Ready. Conversation follows your choices through the lesson.");
    } catch (error) {
      status(error.message, true);
    } finally {
      if (alive) lock(false);
    }
  }
  return { start, render, dispose() { alive = false; generation++; }, getState: () => state };
}

if (typeof window !== "undefined") {
  const ui = createUI(document, window.fetch.bind(window));
  window.addEventListener("pagehide", () => ui.dispose());
  ui.start();
}
