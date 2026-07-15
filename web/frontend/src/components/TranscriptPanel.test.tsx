import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import { TranscriptPanel } from "./TranscriptPanel";
import type { TranscriptEntry } from "../hooks/callSessionReducer";

describe("TranscriptPanel", () => {
  it("shows a placeholder before any transcript exists", () => {
    render(<TranscriptPanel transcripts={[]} />);
    expect(screen.getByText(/transcript will appear here/i)).toBeInTheDocument();
  });

  it("renders user and agent turns with speaker labels", () => {
    const transcripts: TranscriptEntry[] = [
      { id: "1", speaker: "user", text: "Hello there", isFinal: true, timestamp: "t1" },
      { id: "2", speaker: "agent", text: "Hi, how can I help?", isFinal: true, timestamp: "t2" },
    ];
    render(<TranscriptPanel transcripts={transcripts} />);
    expect(screen.getByText("Hello there")).toBeInTheDocument();
    expect(screen.getByText("Hi, how can I help?")).toBeInTheDocument();
    expect(screen.getAllByText("You")).toHaveLength(1);
    expect(screen.getAllByText("Agent")).toHaveLength(1);
  });

  it("exposes the transcript list as an accessible, named region", () => {
    render(<TranscriptPanel transcripts={[]} />);
    expect(screen.getByRole("region", { name: /live transcript/i })).toBeInTheDocument();
  });
});
