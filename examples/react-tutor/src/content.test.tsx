import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import { Feedback, LessonContent } from "./App";

describe("canonical course presentation", () => {
  it("shows the full authored question and options, with no HTML injection", () => {
    render(
      <LessonContent
        beat={{
          name: "quiz",
          number: 2,
          text: "What did you learn?",
          options: [{ label: "A", text: "My own explanation" }],
          body: "<script>alert(1)</script>\n\n[Unsafe](javascript:alert(1))",
        }}
      />,
    );
    expect(screen.getByText("What did you learn?")).toBeVisible();
    expect(screen.getByText("My own explanation")).toBeVisible();
    expect(document.querySelector("script")).toBeNull();
    expect(screen.getByText("Unsafe").getAttribute("href")).not.toContain(
      "javascript:",
    );
  });
  it("renders canonical feedback and related objectives without replacing it with narration", () => {
    render(
      <Feedback
        feedback={{
          correct: false,
          reason: "Progress saves your position, not your entire conversation.",
          offered: true,
          objectives: ["saved-progress"],
          label: "B",
          question_number: 1,
        }}
      />,
    );
    expect(
      screen.getByRole("region", { name: "Quiz feedback" }),
    ).toHaveTextContent("Progress saves your position");
    expect(screen.getByText("Your answer: B")).toBeVisible();
    expect(
      screen.getByText("Related objectives: saved-progress"),
    ).toBeVisible();
  });
});
