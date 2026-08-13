import { afterEach, describe, expect, it, vi } from "vitest";
import { getCapabilities, getModelStatus, submitAnalysis } from "./api";

describe("API contract", () => {
  afterEach(() => vi.restoreAllMocks());

  it("submits backend field names", async () => {
    const fetchMock = vi.spyOn(globalThis, "fetch").mockResolvedValue(
      new Response(JSON.stringify({ id: "job-1", status: "queued" }), { status: 202 }),
    );
    await submitAnalysis({
      file: new File(["image"], "sample.jpg", { type: "image/jpeg" }),
      mode: "image",
      question: "Describe it",
      frames: 16,
      maxPixels: 100000,
      maxTokens: 128,
      segmentSec: 8,
      gateThreshold: 0.5,
    });
    const body = fetchMock.mock.calls[0][1]?.body as FormData;
    expect([...body.keys()]).toEqual([
      "media",
      "mode",
      "question",
      "num_frames",
      "max_pixels",
      "max_new_tokens",
      "segment_sec",
      "gate_threshold",
    ]);
  });

  it("normalizes backend capability and model status shapes", async () => {
    vi.spyOn(globalThis, "fetch")
      .mockResolvedValueOnce(new Response(JSON.stringify({
        model: "microsoft/Mage-VL",
        gpu: { available: true, name: "RTX", vram_total_gb: 8 },
        modes: { image: { supported: true }, streaming: { supported: false, reason: "Missing Decord" } },
      })))
      .mockResolvedValueOnce(new Response(JSON.stringify({
        state: "ready",
        model_id: "microsoft/Mage-VL",
        loaded: true,
      })));
    const capabilities = await getCapabilities();
    const status = await getModelStatus();
    expect(capabilities.gpu).toMatchObject({ available: true, name: "RTX", vramTotalGb: 8 });
    expect(capabilities.modes.streaming).toEqual({ supported: false, reason: "Missing Decord" });
    expect(status).toMatchObject({ loaded: true, model: "microsoft/Mage-VL" });
  });
});
