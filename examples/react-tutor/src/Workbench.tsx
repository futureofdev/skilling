import { useEffect, useRef, useState } from "react";
import { afterVisiblePaint } from "./presentation";
import type { TutorState } from "./types";

const endpoint = `/api/learn/${encodeURIComponent(import.meta.env.VITE_COURSE || "welcome")}`;

async function post(path: string, body: object): Promise<TutorState> {
  const response = await fetch(`${endpoint}${path}`, {
    method: "POST",
    credentials: "same-origin",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
  const value = await response.json();
  if (!response.ok)
    throw new Error(
      value.detail?.message ||
        value.detail ||
        `Request failed (${response.status}). Refresh and try again.`,
    );
  return value;
}

export function Workbench({
  state,
  disabled,
  onState,
  onError,
  onBusy,
}: {
  state: TutorState;
  disabled: boolean;
  onState: (state: TutorState) => void;
  onError: (error: string) => void;
  onBusy: (busy: boolean) => void;
}) {
  const [note, setNote] = useState("");
  const [savedNote, setSavedNote] = useState("");
  const [explanation, setExplanation] = useState("");
  const [busy, setBusy] = useState(false);
  const [notice, setNotice] = useState("");
  const [workLoaded, setWorkLoaded] = useState(false);
  const [reviewAcknowledged, setReviewAcknowledged] = useState<string | null>(
    null,
  );
  const invalidatedReviews = useRef(new Set<string>());
  const reviewElement = useRef<HTMLDivElement>(null);
  const currentReview = useRef(state.review?.id);
  currentReview.current = state.review?.id;
  const callbacks = useRef({ onState, onError });
  callbacks.current = { onState, onError };
  const dirty = note !== savedNote;
  const review = state.review;

  useEffect(() => {
    const controller = new AbortController();
    void fetch("/api/work", {
      credentials: "same-origin",
      signal: controller.signal,
    })
      .then(async (response) => {
        if (!response.ok)
          throw new Error(
            "Could not load your saved work. Refresh the workspace.",
          );
        const data: { text: string } = await response.json();
        setNote(data.text);
        setSavedNote(data.text);
        setWorkLoaded(true);
      })
      .catch((error) => {
        if (!controller.signal.aborted)
          callbacks.current.onError(error.message);
      });
    return () => controller.abort();
  }, []);

  useEffect(() => {
    if (
      !review ||
      !reviewElement.current ||
      dirty ||
      invalidatedReviews.current.has(review.id) ||
      reviewAcknowledged === review.id
    )
      return;
    let cancelled = false;
    const cancelPaint = afterVisiblePaint(reviewElement.current, () => {
      void post("/review/ack", { review_id: review.id })
        .then((next) => {
          if (!cancelled && currentReview.current === review.id) {
            setReviewAcknowledged(review.id);
            callbacks.current.onState(next);
          }
        })
        .catch((error) => {
          if (!cancelled) callbacks.current.onError(error.message);
        });
    });
    return () => {
      cancelled = true;
      cancelPaint();
    };
  }, [review?.id, dirty, reviewAcknowledged]);

  const run = async (action: () => Promise<void>) => {
    setBusy(true);
    onBusy(true);
    try {
      await action();
    } catch (error) {
      onError(
        error instanceof Error ? error.message : "Could not update your work.",
      );
    } finally {
      setBusy(false);
      onBusy(false);
    }
  };
  const locked = disabled || busy;
  const active = state.homework?.active;
  const advice =
    review?.kind === "objectives"
      ? review.advice.objectives
      : review?.advice.requirements;
  const objectiveLabel = (id: string) =>
    state.objectives?.find((item) => item.id === id)?.text || id;
  const reviewFresh = Boolean(
    review &&
      reviewAcknowledged === review.id &&
      !dirty &&
      !invalidatedReviews.current.has(review.id),
  );

  return (
    <section className="workbench" aria-label="Your practice and reflection">
      <details>
        <summary>Your practice & reflection</summary>
        <p className="muted">
          Capture your goal and what you tried. Your tutor can inspect this
          saved note when you ask for a review.
        </p>
        {active && (
          <section className="assignment">
            <h3>{active.title}</h3>
            <p>{active.objective}</p>
            <ol>
              {active.requirements.map((item, index) => (
                <li key={index}>{item.text}</li>
              ))}
            </ol>
            {active.stretch_goals.length > 0 && (
              <>
                <h4>Optional stretch goals</h4>
                <ul>
                  {active.stretch_goals.map((item, index) => (
                    <li key={index}>{item.text}</li>
                  ))}
                </ul>
              </>
            )}
            <p>{active.submission}</p>
          </section>
        )}
        <label htmlFor="work-note">Your learning note</label>
        <textarea
          id="work-note"
          rows={5}
          value={note}
          maxLength={16000}
          disabled={!workLoaded || busy}
          onChange={(event) => {
            if (review) invalidatedReviews.current.add(review.id);
            setNote(event.target.value);
            setReviewAcknowledged(null);
          }}
          placeholder="My goal is… I tried… Here’s what I learned…"
        />
        <div className="button-row">
          <button
            className="learner-button"
            disabled={locked || !dirty || !note.trim()}
            onClick={() =>
              void run(async () => {
                const response = await fetch("/api/work", {
                  method: "PUT",
                  credentials: "same-origin",
                  headers: { "Content-Type": "application/json" },
                  body: JSON.stringify({ text: note }),
                });
                if (!response.ok)
                  throw new Error(
                    `Your note was not saved (${response.status}).`,
                  );
                setSavedNote(note);
                setNotice(
                  "Your note is saved. Request a fresh review after any edits.",
                );
                setReviewAcknowledged(null);
              })
            }
          >
            Save my note <span aria-hidden="true">→</span>
          </button>
          <span className="muted" role="status">
            {dirty
              ? "Unsaved changes"
              : notice ||
                (savedNote ? "Saved note loaded" : "No saved note yet")}
          </span>
        </div>
        <label htmlFor="review-explanation">
          Explain what you understand and what you did
        </label>
        <textarea
          id="review-explanation"
          rows={3}
          value={explanation}
          maxLength={8000}
          onChange={(event) => setExplanation(event.target.value)}
          placeholder="Use your own words and point to the work you’d like reviewed."
        />
        <div className="button-row">
          <button
            className="system-button"
            disabled={locked || dirty || !explanation.trim()}
            onClick={() =>
              void run(async () => {
                setReviewAcknowledged(null);
                onState(
                  await post("/review", { kind: "objectives", explanation }),
                );
              })
            }
          >
            {busy ? "Working…" : "Review my learning"}
          </button>
          {active && (
            <button
              className="system-button"
              disabled={locked || dirty || !explanation.trim()}
              onClick={() =>
                void run(async () => {
                  setReviewAcknowledged(null);
                  onState(
                    await post("/review", { kind: "homework", explanation }),
                  );
                })
              }
            >
              Review my homework
            </button>
          )}
        </div>
      </details>
      {review && (
        <div className="review-panel" ref={reviewElement}>
          <span className="eyebrow">
            TUTOR ADVICE · REVIEW BEFORE CONFIRMING
          </span>
          <p className="muted">
            This advice is informal. You decide whether it accurately represents
            your own work.
          </p>
          {advice?.map((item) => (
            <article key={item.id}>
              <h3>
                {review.kind === "objectives"
                  ? objectiveLabel(item.id)
                  : active?.requirements[Number(item.id.split("/").at(-1)) - 1]
                      ?.text || item.id}
              </h3>
              <span className="verdict">
                {item.verdict.replaceAll("-", " ")}
              </span>
              <p>{item.reason}</p>
            </article>
          ))}
          {review.advice.stretch_goals?.map((item) => (
            <article key={item.id}>
              <h3>Optional: {item.id}</h3>
              <span className="verdict">
                {item.verdict.replaceAll("-", " ")}
              </span>
              <p>{item.reason}</p>
            </article>
          ))}
          {(dirty || invalidatedReviews.current.has(review.id)) && (
            <p className="muted">
              Your work changed. Save it and request a fresh review before
              confirming.
            </p>
          )}
          {review.kind === "objectives" ? (
            advice
              ?.filter(
                (item) =>
                  item.verdict === "supported" &&
                  review.objective_ids.includes(item.id),
              )
              .map((item) => (
                <button
                  key={item.id}
                  className="learner-button"
                  disabled={locked || !reviewFresh}
                  onClick={() =>
                    void run(async () =>
                      onState(
                        await post("/review/confirm", {
                          review_id: review.id,
                          objective_id: item.id,
                        }),
                      ),
                    )
                  }
                >
                  I confirm my own work: {objectiveLabel(item.id)}
                </button>
              ))
          ) : (
            <button
              className="learner-button"
              disabled={
                locked ||
                !reviewFresh ||
                advice?.some((item) => item.verdict !== "supported")
              }
              onClick={() =>
                void run(async () =>
                  onState(
                    await post("/review/confirm", { review_id: review.id }),
                  ),
                )
              }
            >
              I reviewed every requirement — submit my homework
            </button>
          )}
        </div>
      )}
    </section>
  );
}
