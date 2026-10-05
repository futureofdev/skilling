import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import { TranscriptMessageView } from "./App";
import { historyMessages, type TutorState } from "./types";

function transcript(messages: TutorState["messages"]) {
  const state = { messages } as TutorState;
  return historyMessages(state);
}

describe("canonical transcript chronology", () => {
  it("keeps the question, learner answer, feedback and next question in their original order", () => {
    const messages = transcript([
      { role: "tutor", text: "Let’s check what you learned." },
      {
        role: "tutor",
        text: "",
        kind: "quiz",
        coordinate: "1.1",
        question: {
          number: 1,
          text: "Where does learning progress live?",
          options: [{ label: "a", text: "In your workspace" }],
        },
      },
      { role: "learner", text: "In my workspace." },
      {
        role: "tutor",
        text: "",
        kind: "feedback",
        coordinate: "1.1",
        feedback: {
          correct: true,
          reason: "Your workspace preserves your position.",
          label: "a",
          question_number: 1,
          objectives: ["saved-progress"],
          offered: false,
        },
      },
      {
        role: "tutor",
        text: "",
        kind: "quiz",
        coordinate: "1.2",
        question: {
          number: 2,
          text: "What would you like to practice next?",
          options: [{ label: "a", text: "Writing a small program" }],
        },
      },
      { role: "tutor", text: "We can explore that together." },
    ]);
    render(
      <div>
        {messages.map((message) => (
          <TranscriptMessageView key={message.id} message={message} />
        ))}
      </div>,
    );
    const articles = screen.getAllByRole("article");
    expect(articles).toHaveLength(6);
    expect(articles[1]).toHaveTextContent("Where does learning progress live?");
    expect(articles[2]).toHaveTextContent("In my workspace.");
    expect(articles[3]).toHaveTextContent(
      "Your workspace preserves your position.",
    );
    expect(articles[3]).toHaveTextContent("Lesson 1.1");
    expect(articles[4]).toHaveTextContent(
      "What would you like to practice next?",
    );
    expect(articles[4]).toHaveTextContent("Lesson 1.2");
    expect(
      screen.getAllByRole("region", { name: "Quiz feedback" }),
    ).toHaveLength(1);
  });

  it("restores structured entries with empty text without adding fake learner messages", () => {
    const messages = transcript([
      {
        role: "tutor",
        text: "",
        kind: "quiz",
        question: { number: 3, text: "Which comes next?", options: [] },
      },
      {
        role: "tutor",
        text: "",
        kind: "feedback",
        feedback: {
          correct: false,
          reason: "Review the sequence.",
          offered: true,
          objectives: [],
        },
      },
    ]);
    expect(messages.map((message) => message.role)).toEqual([
      "assistant",
      "assistant",
    ]);
    expect(messages.map((message) => message.parts[0].type)).toEqual([
      "data-presentation",
      "data-presentation",
    ]);
    render(
      <div>
        {messages.map((message) => (
          <TranscriptMessageView key={message.id} message={message} />
        ))}
      </div>,
    );
    expect(screen.getByText("Which comes next?")).toBeVisible();
    expect(screen.getByText("Review the sequence.")).toBeVisible();
  });
});
