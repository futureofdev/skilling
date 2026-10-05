import { useCallback, useEffect, useRef, useState } from "react";
import { useChat } from "@ai-sdk/react";
import { DefaultChatTransport } from "ai";
import Markdown from "react-markdown";
import remarkGfm from "remark-gfm";
import { Workbench } from "./Workbench";
import { afterVisiblePaint } from "./presentation";
import {
  historyMessages,
  type ActionBody,
  type Beat,
  type TutorMessage,
  type TutorState,
} from "./types";

const course = import.meta.env.VITE_COURSE || "welcome";
const endpoint = `/api/learn/${encodeURIComponent(course)}`;
const transport = new DefaultChatTransport<TutorMessage>({
  api: `${endpoint}/chat`,
  credentials: "same-origin",
  prepareSendMessagesRequest({ messages, body }) {
    const latest = [...messages]
      .reverse()
      .find((message) => message.role === "user");
    return {
      body: {
        ...body,
        trigger: "submit-message",
        messages:
          body?.continuation_id || body?.message !== undefined
            ? []
            : latest
              ? [latest]
              : [],
      },
    };
  },
});

function Prose({ children }: { children: string }) {
  return (
    <div className="prose">
      <Markdown
        remarkPlugins={[remarkGfm]}
        skipHtml
        components={{
          a: ({ children, ...props }) => (
            <a {...props} target="_blank" rel="noopener noreferrer">
              {children}
            </a>
          ),
        }}
      >
        {children}
      </Markdown>
    </div>
  );
}

export function LessonContent({ beat }: { beat: Beat }) {
  return (
    <>
      {beat.body && <Prose>{beat.body}</Prose>}
      {beat.objectives?.length ? (
        <section className="objectives">
          <h3>What you’ll take away</h3>
          <ul>
            {beat.objectives.map((item, i) => (
              <li key={i}>{item}</li>
            ))}
          </ul>
        </section>
      ) : null}
      {beat.key_terms && (
        <details>
          <summary>Key terms</summary>
          <Prose>{beat.key_terms}</Prose>
        </details>
      )}
      {beat.objective && <Prose>{beat.objective}</Prose>}
      {beat.text && (
        <section className="question">
          <span className="eyebrow">
            Check your understanding {beat.number ? ` / ${beat.number}` : ""}
          </span>
          <Prose>{beat.text}</Prose>
          <ul className="option-list">
            {beat.options?.map((option) => (
              <li key={option.label}>
                <strong>{option.label}</strong>
                <span>{option.text}</span>
              </li>
            ))}
          </ul>
        </section>
      )}
      {beat.offer_revisit && (
        <p className="muted">
          You can ask your tutor to revisit this idea before you continue.
        </p>
      )}
    </>
  );
}

export function Feedback({
  feedback,
}: {
  feedback: NonNullable<TutorState["feedback"]>;
}) {
  return (
    <section
      className={`feedback ${feedback.correct ? "correct" : ""}`}
      aria-label="Quiz feedback"
    >
      <span className="eyebrow">
        {feedback.question_number
          ? `Question ${feedback.question_number} · `
          : ""}
        Quiz feedback
      </span>
      <h3>
        {feedback.correct ? "You’ve got it." : "Let’s look at that together."}
      </h3>
      {feedback.label && <p>Your answer: {feedback.label}</p>}
      <Prose>{feedback.reason}</Prose>
      {feedback.objectives.length > 0 && (
        <p>Related objectives: {feedback.objectives.join(", ")}</p>
      )}
      {feedback.offered && (
        <p>You can revisit the explanation with your tutor.</p>
      )}
    </section>
  );
}

export function TranscriptMessageView({ message }: { message: TutorMessage }) {
  const lastReset = message.parts.reduce(
    (last, part, index) =>
      part.type === "data-skilling" && part.data.type === "text-reset"
        ? index
        : last,
    -1,
  );
  const presentation = message.parts.find(
    (part) => part.type === "data-presentation",
  );
  return (
    <article className={`message ${message.role}`} key={message.id}>
      <div className="message-author">
        {message.role === "user"
          ? "YOU"
          : presentation?.type === "data-presentation"
            ? presentation.data.kind === "quiz"
              ? "COURSE QUESTION"
              : "COURSE FEEDBACK"
            : "SKILLING TUTOR"}
      </div>
      <div className="message-content">
        {message.parts.map((part, index) => {
          if (part.type === "text" && index > lastReset)
            return <Prose key={index}>{part.text}</Prose>;
          if (part.type !== "data-presentation") return null;
          return (
            <div key={index}>
              {part.data.coordinate && (
                <p className="eyebrow text-muted mb-3">
                  Lesson {part.data.coordinate}
                </p>
              )}
              {part.data.kind === "quiz" ? (
                <LessonContent beat={{ name: "quiz", ...part.data.question }} />
              ) : (
                <Feedback feedback={part.data.feedback} />
              )}
            </div>
          );
        })}
      </div>
    </article>
  );
}

export function App() {
  const [state, setState] = useState<TutorState | null>(null);
  const [input, setInput] = useState("");
  const [problem, setProblem] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);
  const [acknowledging, setAcknowledging] = useState(false);
  const [acknowledged, setAcknowledged] = useState<string | null>(null);
  const [workBusy, setWorkBusy] = useState(false);
  const canonicalState = useRef<TutorState | null>(null);
  const [outlineOpen, setOutlineOpen] = useState(false);
  const [referenceOpen, setReferenceOpen] = useState(false);
  const [referenceRequest, setReferenceRequest] = useState(0);
  const referenceSection = useRef<HTMLDetailsElement>(null);
  const [narrowViewport, setNarrowViewport] = useState(
    () =>
      typeof window.matchMedia === "function" &&
      window.matchMedia("(max-width: 800px)").matches,
  );
  const [streamNotice, setStreamNotice] = useState("");
  const [showLatest, setShowLatest] = useState(false);
  const scrollArea = useRef<HTMLDivElement>(null);
  const thread = useRef<HTMLDivElement>(null);
  const followLatest = useRef(true);
  const contextToggle = useRef<HTMLButtonElement>(null);
  const display = useRef<HTMLDivElement>(null);
  const composer = useRef<HTMLTextAreaElement>(null);
  const lastAction = useRef<ActionBody>({});
  const currentDisplay = useRef<string | null>(null);
  const ackRequests = useRef(new Set<string>());
  const continued = useRef(new Set<string>());
  const mounted = useRef(true);
  const acceptState = useCallback((next: TutorState) => {
    currentDisplay.current = next.display_id;
    canonicalState.current = next;
    setState(next);
  }, []);
  const {
    messages,
    setMessages,
    sendMessage,
    regenerate,
    stop,
    status,
    error,
    clearError,
  } = useChat<TutorMessage>({
    transport,
    onData(part) {
      if (part.type !== "data-skilling") return;
      if (part.data.type === "state") {
        setStreamNotice(
          part.data.state.feedback
            ? "Your feedback is ready."
            : "Updating your place…",
        );
        acceptState(part.data.state);
      } else if (part.data.type === "text-reset") {
        setStreamNotice("Refining your explanation…");
      } else {
        if (part.data.state) acceptState(part.data.state);
        setStreamNotice("");
        setProblem(part.data.message);
      }
    },
    onFinish() {
      setStreamNotice("");
      if (canonicalState.current)
        setMessages(historyMessages(canonicalState.current));
    },
  });
  const streaming = status === "submitted" || status === "streaming";
  const failure = problem || error?.message;
  const ready = Boolean(
    state &&
      acknowledged === state.display_id &&
      !streaming &&
      !acknowledging &&
      !loading &&
      !failure &&
      !workBusy,
  );

  const load = useCallback(
    async (signal?: AbortSignal) => {
      setLoading(true);
      setProblem(null);
      clearError();
      try {
        const response = await fetch(`${endpoint}/state`, {
          credentials: "same-origin",
          signal,
        });
        if (!response.ok)
          throw new Error(
            `Could not load your workspace (${response.status}). Check that the tutor server is running.`,
          );
        const next: TutorState = await response.json();
        if (signal?.aborted || !mounted.current) return;
        ackRequests.current.clear();
        continued.current.clear();
        setAcknowledged(null);
        setMessages(historyMessages(next));
        acceptState(next);
      } catch (cause) {
        if (!signal?.aborted && mounted.current)
          setProblem(
            cause instanceof Error
              ? cause.message
              : "Could not load your workspace.",
          );
      } finally {
        if (!signal?.aborted && mounted.current) setLoading(false);
      }
    },
    [acceptState, clearError, setMessages],
  );

  useEffect(() => {
    mounted.current = true;
    const controller = new AbortController();
    void load(controller.signal);
    return () => {
      mounted.current = false;
      controller.abort();
    };
  }, [load]);

  // Only acknowledge canonical content after this exact, completed display has
  // committed and had a visible paint. Streaming tokens alone are not evidence.
  useEffect(() => {
    if (
      !state ||
      !display.current ||
      streaming ||
      loading ||
      failure ||
      acknowledged === state.display_id ||
      (outlineOpen && narrowViewport)
    )
      return;
    const id = state.display_id;
    return afterVisiblePaint(display.current, () => {
      if (ackRequests.current.has(id)) return;
      ackRequests.current.add(id);
      setAcknowledging(true);
      void fetch(`${endpoint}/ack`, {
        method: "POST",
        credentials: "same-origin",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ display_id: id }),
      })
        .then(async (response) => {
          if (!response.ok)
            throw new Error(
              `Your progress needs to be refreshed (${response.status}).`,
            );
          const next: TutorState = await response.json();
          if (mounted.current && currentDisplay.current === id) {
            acceptState(next);
            setMessages(historyMessages(next));
            setAcknowledged(next.display_id);
          }
        })
        .catch((cause) => {
          if (mounted.current)
            setProblem(
              cause instanceof Error
                ? cause.message
                : "Could not confirm the displayed lesson.",
            );
        })
        .finally(() => {
          if (mounted.current) setAcknowledging(false);
        });
    });
  }, [
    state,
    streaming,
    loading,
    failure,
    acknowledged,
    acceptState,
    outlineOpen,
    narrowViewport,
    setMessages,
  ]);

  const send = useCallback(
    (text: string, action: ActionBody = {}) => {
      const body = {
        request_id: crypto.randomUUID(),
        display_id: currentDisplay.current || undefined,
        message: text,
        ...action,
      };
      lastAction.current = body;
      followLatest.current = true;
      setStreamNotice("Preparing your reply…");
      setProblem(null);
      clearError();
      void sendMessage({ text }, { body });
    },
    [sendMessage, clearError],
  );

  useEffect(() => {
    const id = state?.continuation?.id;
    if (!ready || !id || continued.current.has(id)) return;
    continued.current.add(id);
    const body = { request_id: crypto.randomUUID(), continuation_id: id };
    lastAction.current = body;
    // No invented learner utterance: this is a server-issued continuation.
    void sendMessage(
      { role: "user", parts: [], id: body.request_id },
      { body },
    );
  }, [ready, state?.continuation?.id, sendMessage]);

  const submit = () => {
    if (!ready || !input.trim()) return;
    send(input.trim());
    setInput("");
  };
  const completed = state?.snapshot.completed_count ?? 0;
  const total = state?.snapshot.lesson_count ?? 0;
  const beat = state?.snapshot.beat;
  const percent = total ? Math.round((completed / total) * 100) : 0;
  const position = state?.snapshot.position;
  const coordinate = position ? `${position.phase}.${position.lesson}` : "";
  const title = state?.snapshot.course.title || "Your learning workspace";
  const meaningfulMessages = messages.filter((message) =>
    message.parts.some(
      (part) =>
        part.type === "data-presentation" ||
        (part.type === "text" && part.text.trim()),
    ),
  );

  const scrollToLatest = useCallback(() => {
    const viewport = scrollArea.current;
    if (!viewport) return;
    followLatest.current = true;
    viewport.scrollTop = viewport.scrollHeight;
    setShowLatest(false);
  }, []);

  useEffect(() => {
    const content = thread.current;
    const update = () => {
      if (followLatest.current) scrollToLatest();
      else setShowLatest(true);
    };
    update();
    if (!content || typeof ResizeObserver === "undefined") return;
    const observer = new ResizeObserver(update);
    observer.observe(content);
    return () => observer.disconnect();
  }, [messages, state?.display_id, streaming, outlineOpen, scrollToLatest]);

  useEffect(() => {
    if (!outlineOpen) return;
    const close = (event: KeyboardEvent) => {
      if (event.key !== "Escape") return;
      setOutlineOpen(false);
      contextToggle.current?.focus();
    };
    document.addEventListener("keydown", close);
    return () => document.removeEventListener("keydown", close);
  }, [outlineOpen]);

  useEffect(() => {
    if (typeof window.matchMedia !== "function") return;
    const query = window.matchMedia("(max-width: 800px)");
    const update = () => setNarrowViewport(query.matches);
    update();
    query.addEventListener("change", update);
    return () => query.removeEventListener("change", update);
  }, []);

  const openLessonReference = () => {
    setOutlineOpen(true);
    setReferenceOpen(true);
    setReferenceRequest((value) => value + 1);
  };
  useEffect(() => {
    if (!outlineOpen || !referenceOpen || referenceRequest === 0) return;
    const frame = requestAnimationFrame(() => {
      referenceSection.current?.scrollIntoView?.({
        block: "start",
        behavior: "auto",
      });
      referenceSection.current
        ?.querySelector("summary")
        ?.focus({ preventScroll: true });
    });
    return () => cancelAnimationFrame(frame);
  }, [outlineOpen, referenceOpen, referenceRequest]);

  const streamedReply = messages.at(-1);
  const resetIndex =
    streamedReply?.parts.reduce(
      (last, part, index) =>
        part.type === "data-skilling" && part.data.type === "text-reset"
          ? index
          : last,
      -1,
    ) ?? -1;
  const hasLiveText =
    streamedReply?.role === "assistant" &&
    streamedReply.parts.some(
      (part, index) =>
        index > resetIndex && part.type === "text" && part.text.length > 0,
    );
  const activity = failure
    ? "Connection needs your attention"
    : workBusy
      ? "Reviewing your work…"
      : acknowledging
        ? "Saving your place…"
        : streaming
          ? hasLiveText
            ? "Responding…"
            : streamNotice ||
              (status === "submitted" ? "Preparing your reply…" : "Responding…")
          : loading
            ? "Opening your workspace…"
            : "Ready when you are";
  const hasCurrentQuestion = meaningfulMessages.some((message) =>
    message.parts.some(
      (part) =>
        part.type === "data-presentation" &&
        part.data.kind === "quiz" &&
        part.data.question.text === beat?.text &&
        part.data.question.number === beat?.number &&
        (!part.data.coordinate || part.data.coordinate === coordinate),
    ),
  );
  const hasCurrentFeedback = meaningfulMessages.some((message) =>
    message.parts.some(
      (part) =>
        part.type === "data-presentation" &&
        part.data.kind === "feedback" &&
        state?.feedback &&
        part.data.feedback.question_number === state.feedback.question_number &&
        part.data.feedback.label === state.feedback.label &&
        part.data.feedback.reason === state.feedback.reason &&
        (!part.data.coordinate || part.data.coordinate === coordinate),
    ),
  );

  return (
    <div className="chat-app">
      <a className="skip-link" href="#conversation">
        Skip to conversation
      </a>
      <header className="chat-header">
        <a
          className="wordmark"
          href="/"
          aria-label="Skilling learning workspace"
        >
          <img src="/skilling-mark.svg" width="28" height="28" alt="" />
          <span>skilling</span>
        </a>
        <div className="header-course">
          <span>{title}</span>
          <small>
            {position ? `Lesson ${coordinate}` : "Your learning workspace"}
          </small>
        </div>
        <button
          ref={contextToggle}
          type="button"
          className={`context-toggle ${outlineOpen ? "active" : ""}`}
          aria-expanded={outlineOpen}
          aria-controls="learning-context"
          onClick={() => setOutlineOpen(!outlineOpen)}
        >
          <span className="panel-icon" aria-hidden="true">
            ◧
          </span>
          {outlineOpen ? "Hide context" : "Course & notes"}
        </button>
      </header>
      <div className={`chat-layout ${outlineOpen ? "context-open" : ""}`}>
        <main className="chat-main" aria-label="Learning conversation">
          <div
            className="chat-scroll"
            id="conversation"
            ref={scrollArea}
            tabIndex={0}
            aria-label="Conversation — scroll to explore previous messages"
            onScroll={() => {
              const element = scrollArea.current;
              if (!element) return;
              const nearBottom =
                element.scrollHeight -
                  element.scrollTop -
                  element.clientHeight <
                96;
              followLatest.current = nearBottom;
              if (nearBottom) setShowLatest(false);
            }}
          >
            <div className="chat-thread" ref={thread}>
              <div className="chat-intro">
                <span className="eyebrow">YOUR SPACE TO LEARN</span>
                <h1>
                  {meaningfulMessages.length
                    ? "Keep the conversation going."
                    : "Let’s make something click."}
                </h1>
                <p>Ask, explore, and think out loud. We’ll go at your pace.</p>
              </div>
              {loading && (
                <p className="loading-state" role="status">
                  Loading your course and saved progress…
                </p>
              )}
              {meaningfulMessages.map((message) => (
                <TranscriptMessageView key={message.id} message={message} />
              ))}
              <div
                className="current-presentation"
                data-display-id={state?.display_id}
              >
                {beat?.text && !hasCurrentQuestion ? (
                  <article
                    className="inline-material"
                    aria-label="Current quiz question"
                  >
                    <LessonContent
                      beat={{
                        name: beat.name,
                        text: beat.text,
                        number: beat.number,
                        options: beat.options,
                      }}
                    />
                  </article>
                ) : (
                  beat && (
                    <div className="current-lesson-marker">
                      <span>
                        Lesson {coordinate}
                        {beat.title ? ` · ${beat.title}` : ""}
                      </span>
                      <button type="button" onClick={openLessonReference}>
                        Lesson reference <span aria-hidden="true">↗</span>
                      </button>
                    </div>
                  )
                )}
                {state?.feedback && !hasCurrentFeedback && (
                  <div className="inline-feedback">
                    <Feedback feedback={state.feedback} />
                  </div>
                )}
                {state?.celebration && (
                  <section className="feedback correct">
                    <span className="eyebrow">
                      {state.celebration.course_complete
                        ? "COURSE COMPLETE"
                        : "PHASE COMPLETE"}
                    </span>
                    <h3>{state.celebration.phase_name}</h3>
                    <Prose>{state.celebration.phase_highlight}</Prose>
                    <p className="muted">{state.celebration.share_text}</p>
                  </section>
                )}
              </div>
              {!meaningfulMessages.length && !loading && (
                <div className="chat-welcome">
                  <span className="tutor-avatar">
                    <img
                      src="/skilling-mark.svg"
                      alt=""
                      width="20"
                      height="20"
                    />
                  </span>
                  <div>
                    <h2>Start with a little curiosity.</h2>
                    <p>
                      Tell me what you’d like to get out of this, or ask me to
                      explain the idea above.
                    </p>
                    <div className="suggestions">
                      {["Walk me through this", "Show me an example"].map(
                        (text) => (
                          <button
                            key={text}
                            disabled={!ready}
                            onClick={() => send(text)}
                          >
                            {text}
                            <span aria-hidden="true">↗</span>
                          </button>
                        ),
                      )}
                    </div>
                  </div>
                </div>
              )}
              {state && state.controls.length > 0 && (
                <section
                  className="next-step"
                  aria-label="Choose your next step"
                >
                  <span className="eyebrow">
                    {beat?.text ? "YOUR ANSWER" : "WHEN YOU’RE READY"}
                  </span>
                  <div
                    className={beat?.text ? "answer-controls" : "button-row"}
                  >
                    {state.controls.map((control) => (
                      <button
                        className="learner-button"
                        key={control.id}
                        disabled={!ready}
                        onClick={() =>
                          send(control.label, {
                            control: control.id,
                            display_id: state.display_id,
                          })
                        }
                      >
                        {control.label}
                        <span aria-hidden="true">→</span>
                      </button>
                    ))}
                  </div>
                </section>
              )}
              {streaming && (
                <div className="reply-activity" aria-hidden="true">
                  <span className="typing-indicator" />
                  <span>{activity}</span>
                  <span className="stream-bars">
                    <i />
                    <i />
                    <i />
                  </span>
                </div>
              )}
              {failure && (
                <section className="error-panel" role="alert">
                  <h3>Let’s reconnect.</h3>
                  <p>{failure}</p>
                  <div className="button-row">
                    <button
                      className="system-button"
                      onClick={() => void load()}
                      disabled={streaming}
                    >
                      Refresh workspace
                    </button>
                    {lastAction.current.request_id && (
                      <button
                        className="text-button"
                        disabled={streaming}
                        onClick={() => {
                          setProblem(null);
                          clearError();
                          setStreamNotice("Trying your last turn again…");
                          followLatest.current = true;
                          void regenerate({ body: lastAction.current });
                        }}
                      >
                        Retry last turn
                      </button>
                    )}
                  </div>
                </section>
              )}
              <div ref={display} className="presentation-receipt" />
            </div>
          </div>
          {showLatest && (
            <button className="jump-latest" onClick={scrollToLatest}>
              Back to latest <span aria-hidden="true">↓</span>
            </button>
          )}
          <div className="composer-dock">
            <div className="composer-width">
              <div
                className="chat-activity"
                role="status"
                aria-live="polite"
                aria-atomic="true"
              >
                <span
                  className={
                    streaming || acknowledging || workBusy
                      ? "typing-indicator"
                      : "idle-indicator"
                  }
                />
                <span>{activity}</span>
                {!streaming && !failure && state && (
                  <span className="activity-lesson">Lesson {coordinate}</span>
                )}
              </div>
              <form
                className="composer"
                onSubmit={(event) => {
                  event.preventDefault();
                  submit();
                }}
              >
                <label htmlFor="message">Make room for a question.</label>
                <div className="input-row">
                  <textarea
                    id="message"
                    ref={composer}
                    maxLength={8000}
                    value={input}
                    rows={2}
                    placeholder="Message your tutor…"
                    disabled={loading || !state}
                    onChange={(event) => setInput(event.target.value)}
                    onKeyDown={(event) => {
                      if (
                        event.key === "Enter" &&
                        !event.shiftKey &&
                        !event.nativeEvent.isComposing
                      ) {
                        event.preventDefault();
                        submit();
                      }
                    }}
                  />
                  {streaming ? (
                    <button
                      type="button"
                      className="system-button stop-button"
                      onClick={() => {
                        void stop();
                        setStreamNotice("");
                        setProblem(
                          "Response stopped. Refresh to recover the latest saved progress, or retry the same turn.",
                        );
                      }}
                    >
                      <span aria-hidden="true">■</span> Stop
                    </button>
                  ) : (
                    <button
                      className="send-button"
                      type="submit"
                      disabled={!ready || !input.trim()}
                      aria-label="Send message"
                    >
                      ↑
                    </button>
                  )}
                </div>
                <div className="composer-footer">
                  <span>Enter to send · Shift + Enter for a new line</span>
                  <button
                    type="button"
                    className="context-link"
                    onClick={() => {
                      setOutlineOpen(true);
                    }}
                  >
                    Your notes & progress <span aria-hidden="true">↗</span>
                  </button>
                </div>
              </form>
              <p className="chat-footnote">
                A conversation is a beginning. What you learn is yours.
              </p>
            </div>
          </div>
        </main>
        <aside
          id="learning-context"
          className="context-panel"
          hidden={!outlineOpen}
          aria-label="Course context and your notes"
        >
          <div className="context-panel-header">
            <span className="eyebrow">YOUR LEARNING CONTEXT</span>
            <button
              type="button"
              aria-label="Close course context"
              onClick={() => {
                setOutlineOpen(false);
                contextToggle.current?.focus();
              }}
            >
              ×
            </button>
          </div>
          <div className="context-panel-content">
            <h2>{title}</h2>
            <p className="muted">
              {position
                ? `Phase ${position.phase} · Lesson ${position.lesson}`
                : "Your course is getting ready"}
            </p>
            <div className="progress-label">
              <span>
                {completed} of {total || "—"} lessons complete
              </span>
              <strong>{percent}%</strong>
            </div>
            <div
              className="progress-track"
              role="progressbar"
              aria-label="Lessons complete"
              aria-valuenow={completed}
              aria-valuemin={0}
              aria-valuemax={total || 1}
            >
              <span style={{ width: `${percent}%` }} />
            </div>
            {state?.outline?.length ? (
              <ol className="outline">
                {state.outline.map((item, index) => (
                  <li
                    key={item.coordinate}
                    className={item.coordinate === coordinate ? "current" : ""}
                    aria-current={
                      item.coordinate === coordinate ? "step" : undefined
                    }
                  >
                    <span
                      className={
                        index < completed
                          ? "lesson-number done"
                          : "lesson-number"
                      }
                    >
                      {index < completed ? "✓" : item.coordinate}
                    </span>
                    <div>
                      {item.title}
                      <small>
                        {index < completed
                          ? "Completed"
                          : item.coordinate === coordinate
                            ? "You are here"
                            : "Ahead"}
                      </small>
                    </div>
                  </li>
                ))}
              </ol>
            ) : null}
            {beat && (
              <details
                ref={referenceSection}
                className="context-lesson"
                open={referenceOpen}
                onToggle={(event) => setReferenceOpen(event.currentTarget.open)}
              >
                <summary>Lesson reference</summary>
                {beat.body ||
                beat.text ||
                beat.key_terms ||
                beat.objective ||
                beat.objectives?.length ? (
                  <LessonContent beat={beat} />
                ) : (
                  <div className="reference-fallback">
                    <p>
                      The tutor’s explanation is in your conversation. At this
                      step, there’s no separate lesson text to show here.
                    </p>
                    <button
                      type="button"
                      className="system-button"
                      onClick={() => {
                        setOutlineOpen(false);
                        setInput(
                          "Could you recap the current lesson and its key ideas?",
                        );
                        requestAnimationFrame(() => composer.current?.focus());
                      }}
                    >
                      Ask for a lesson recap <span aria-hidden="true">↗</span>
                    </button>
                  </div>
                )}
              </details>
            )}
            {state && (
              <Workbench
                state={state}
                disabled={
                  streaming || loading || acknowledging || Boolean(failure)
                }
                onBusy={setWorkBusy}
                onState={(next) => {
                  acceptState(next);
                  setMessages(historyMessages(next));
                }}
                onError={setProblem}
              />
            )}
            {state?.history_notice && (
              <p className="history-notice">{state.history_notice}</p>
            )}
          </div>
        </aside>
      </div>
    </div>
  );
}
