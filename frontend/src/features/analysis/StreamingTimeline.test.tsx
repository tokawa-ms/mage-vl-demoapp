import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import { StreamingTimeline } from "./StreamingTimeline";

describe("StreamingTimeline", () => {
  it("renders timestamps, confidence, decisions and text", () => {
    render(<StreamingTimeline events={[
      { timestamp: 65, probability: .82, decision: "accept", text: "A person enters the room." },
      { timestamp: "01:10", probability: .18, decision: "skip" },
    ]} />);
    expect(screen.getByText("01:05")).toBeInTheDocument();
    expect(screen.getByText("82%")).toBeInTheDocument();
    expect(screen.getByText("accept")).toBeInTheDocument();
    expect(screen.getByText("A person enters the room.")).toBeInTheDocument();
    expect(screen.getByText("No response emitted for this segment.")).toBeInTheDocument();
  });
});
