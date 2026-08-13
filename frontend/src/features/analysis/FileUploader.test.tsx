import { StrictMode } from "react";
import { fireEvent, render, screen } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { FileUploader } from "./FileUploader";

describe("FileUploader", () => {
  beforeEach(() => {
    let sequence = 0;
    vi.stubGlobal("URL", {
      ...URL,
      createObjectURL: vi.fn(() => `blob:preview-${++sequence}`),
      revokeObjectURL: vi.fn(),
    });
  });

  afterEach(() => vi.unstubAllGlobals());

  it("renders usable video controls and metadata outside the media surface", () => {
    const file = new File(["video"], "clip.mp4", { type: "video/mp4" });
    const { container } = render(
      <FileUploader file={file} onChange={vi.fn()} />,
    );
    const video = screen.getByLabelText("Video preview");
    expect(video).toHaveAttribute("controls");
    expect(video).toHaveAttribute("playsinline");
    expect(video).toHaveAttribute("preload", "metadata");
    expect(container.querySelector(".media-meta")?.parentElement)
      .toBe(container.querySelector(".media-preview"));
  });

  it("shows a codec fallback without blocking analysis", () => {
    const file = new File(["video"], "clip.mp4", { type: "video/mp4" });
    render(<FileUploader file={file} onChange={vi.fn()} />);
    fireEvent.error(screen.getByLabelText("Video preview"));
    expect(screen.getByRole("status")).toHaveTextContent(
      "Mage-VL can still analyze it",
    );
  });

  it("recreates the object URL after StrictMode effect cleanup", () => {
    const file = new File(["video"], "clip.mp4", { type: "video/mp4" });
    render(
      <StrictMode>
        <FileUploader file={file} onChange={vi.fn()} />
      </StrictMode>,
    );
    expect(URL.createObjectURL).toHaveBeenCalledTimes(2);
    expect(URL.revokeObjectURL).toHaveBeenCalledWith("blob:preview-1");
    expect(screen.getByLabelText("Video preview"))
      .toHaveAttribute("src", "blob:preview-2");
  });
});
