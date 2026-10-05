import type { UIMessage } from "ai";

export interface Control {
  id: string;
  label: string;
  operation: string;
  payload: string;
}
export interface Beat {
  name: string;
  title?: string;
  body?: string;
  key_terms?: string;
  objectives?: string[];
  objective?: string;
  text?: string;
  number?: number;
  options?: { label: string; text: string }[];
  offer_revisit?: boolean;
}
export interface TutorState {
  display_id: string;
  snapshot: {
    course: { id: string; title: string; version: string };
    position: { phase: number; lesson: number; beat: string | null };
    revision: string | null;
    beat: Beat;
    completed_count: number;
    lesson_count: number;
    legal_inputs: string[];
  };
  controls: Control[];
  feedback: {
    display_id?: string;
    correct: boolean;
    reason: string;
    label?: string;
    question_number?: number;
    offered: boolean;
    objectives: string[];
  } | null;
  messages: TranscriptMessage[];
  continuation: { id: string } | null;
  history_notice: string;
  objectives?: {
    id: string;
    kind: string;
    text: string;
    verify?: string;
    settleable_now: boolean;
  }[];
  homework?: {
    active: {
      title: string;
      objective: string;
      requirements: { text: string }[];
      stretch_goals: { text: string }[];
      submission: string;
    } | null;
  } | null;
  review?: Review | null;
  course_complete?: boolean;
  celebration?: {
    coordinate: string;
    phase_name: string;
    phase_highlight: string;
    share_text: string;
    course_complete: boolean;
  } | null;
  outline?: {
    coordinate: string;
    title: string;
    completed?: boolean;
    current?: boolean;
  }[];
}
export interface Review {
  id: string;
  kind: "objectives" | "homework";
  displayed: boolean;
  objective_ids: string[];
  advice: {
    objectives?: AdviceItem[];
    requirements?: AdviceItem[];
    stretch_goals?: AdviceItem[];
  };
}
export interface AdviceItem {
  id: string;
  verdict: "supported" | "partial" | "not-yet";
  reason: string;
}
export type SkillingEvent =
  | { type: "state"; state: TutorState }
  | { type: "text-reset" }
  | { type: "error"; code: string; message: string; state?: TutorState };
export interface QuizQuestion {
  number: number;
  text: string;
  options: { label: string; text: string }[];
}
export type CanonicalPresentation =
  | { kind: "quiz"; question: QuizQuestion; coordinate?: string }
  | {
      kind: "feedback";
      feedback: NonNullable<TutorState["feedback"]>;
      coordinate?: string;
    };
export type TranscriptMessage =
  | { role: "learner" | "tutor"; text: string; kind?: undefined }
  | ({ role: "tutor"; text: string } & CanonicalPresentation);
export type TutorMessage = UIMessage<
  unknown,
  {
    skilling: SkillingEvent;
    presentation: CanonicalPresentation;
  }
>;
export type ActionBody = {
  message?: string;
  request_id?: string;
  display_id?: string;
  control?: string;
  continuation_id?: string;
};

export function historyMessages(state: TutorState): TutorMessage[] {
  return state.messages.map((message, index) => ({
    id: `history-${index}`,
    role: message.role === "learner" ? "user" : "assistant",
    parts:
      message.kind === "quiz"
        ? [
            {
              type: "data-presentation",
              data: {
                kind: "quiz",
                question: message.question,
                coordinate: message.coordinate,
              },
            },
          ]
        : message.kind === "feedback"
          ? [
              {
                type: "data-presentation",
                data: {
                  kind: "feedback",
                  feedback: message.feedback,
                  coordinate: message.coordinate,
                },
              },
            ]
          : [{ type: "text", text: message.text }],
  }));
}
