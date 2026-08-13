import { fireEvent, render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import type { Capabilities } from "../../types/api";
import { AnalysisForm } from "./AnalysisForm";

const capabilities: Capabilities = {
  modes: {
    image: { supported: true },
    video_frames: { supported: true },
    traditional_codec: { supported: false, reason: "FFmpeg is not installed" },
    neural_codec: { supported: true },
    streaming: { supported: true },
  },
  gpu: { available: false },
};

describe("AnalysisForm", () => {
  it("shows controls for the selected mode", () => {
    render(<AnalysisForm capabilities={capabilities} onSubmit={vi.fn()} />);
    expect(screen.queryByLabelText("Sample frames")).not.toBeInTheDocument();
    fireEvent.click(screen.getByLabelText(/Stream/));
    expect(screen.getByLabelText("Sample frames")).toBeInTheDocument();
    expect(screen.getByLabelText("Segment seconds")).toBeInTheDocument();
    expect(screen.getByLabelText("Gate threshold")).toBeInTheDocument();
  });

  it("disables unsupported capabilities and explains why", () => {
    render(<AnalysisForm capabilities={capabilities} onSubmit={vi.fn()} />);
    const codec = screen.getByLabelText(/Codec/);
    expect(codec).toBeDisabled();
    expect(screen.getByText("FFmpeg is not installed")).toBeInTheDocument();
  });

  it("rounds max pixels down to the nearest supported value", () => {
    render(<AnalysisForm capabilities={capabilities} onSubmit={vi.fn()} />);
    const maxPixels = screen.getByLabelText("Max pixels");
    expect(maxPixels).toHaveValue(98304);
    fireEvent.change(maxPixels, { target: { value: "100000" } });
    fireEvent.blur(maxPixels);
    expect(maxPixels).toHaveValue(98304);
    fireEvent.change(maxPixels, { target: { value: "114687" } });
    fireEvent.blur(maxPixels);
    expect(maxPixels).toHaveValue(98304);
    fireEvent.change(maxPixels, { target: { value: "114688" } });
    fireEvent.blur(maxPixels);
    expect(maxPixels).toHaveValue(114688);
  });
});
