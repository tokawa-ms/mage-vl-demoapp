import { act, renderHook, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import { useAnalysisJob } from "./useAnalysisJob";

class MockEventSource {
  static instance: MockEventSource;
  listeners = new Map<string, EventListener>();
  onopen: (() => void) | null = null;
  onmessage: ((event: MessageEvent) => void) | null = null;
  onerror: (() => void) | null = null;
  close = vi.fn();
  addEventListener = vi.fn((name: string, listener: EventListener) => {
    this.listeners.set(name, listener);
  });
  constructor(public url: string) { MockEventSource.instance = this; }
}

describe("useAnalysisJob", () => {
  afterEach(() => vi.restoreAllMocks());

  it("handles SSE updates and recovers state after a connection error", async () => {
    vi.stubGlobal("EventSource", MockEventSource);
    const fetchMock = vi.spyOn(globalThis, "fetch")
      .mockResolvedValueOnce(new Response(JSON.stringify({ id: "job-1", status: "queued", progress: 0 }), { status: 200 }))
      .mockResolvedValueOnce(new Response(JSON.stringify({ id: "job-1", status: "completed", progress: 100, result: { answer: "Recovered" } }), { status: 200 }));
    const { result } = renderHook(() => useAnalysisJob());
    await act(async () => {
      await result.current.start({
        file: new File(["x"], "frame.png", { type: "image/png" }),
        mode: "image", question: "What?", frames: 12, maxPixels: 1000, maxTokens: 100, segmentSec: 2, gateThreshold: .5,
      });
    });
    act(() => MockEventSource.instance.onmessage?.(new MessageEvent("message", { data: JSON.stringify({ status: "generating", progress: 60 }) })));
    expect(result.current.job?.status).toBe("generating");
    await act(async () => { MockEventSource.instance.onerror?.(); });
    await waitFor(() => expect(result.current.job?.result?.answer).toBe("Recovered"));
    expect(fetchMock).toHaveBeenCalledWith("/api/analyses/job-1", undefined);
  });

  it("keeps the job active while cancellation is pending", async () => {
    vi.stubGlobal("EventSource", MockEventSource);
    vi.spyOn(globalThis, "fetch")
      .mockResolvedValueOnce(new Response(JSON.stringify({
        id: "job-1", status: "running", progress: 70,
      }), { status: 202 }))
      .mockResolvedValueOnce(new Response(JSON.stringify({
        id: "job-1", status: "running", progress: 70,
        message: "Cancellation requested",
      }), { status: 200 }));
    const { result } = renderHook(() => useAnalysisJob());
    await act(async () => {
      await result.current.start({
        file: new File(["x"], "frame.png", { type: "image/png" }),
        mode: "image", question: "What?", frames: 12, maxPixels: 1000,
        maxTokens: 100, segmentSec: 2, gateThreshold: .5,
      });
    });
    await act(async () => {
      await result.current.cancel();
    });
    expect(result.current.job?.status).toBe("running");
    expect(result.current.job?.message).toBe("Cancellation requested");
    expect(result.current.isActive).toBe(true);
  });
});
