import { act, renderHook } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { useElapsedTime } from "./useElapsedTime";

describe("useElapsedTime", () => {
  beforeEach(() => {
    vi.useFakeTimers();
  });

  afterEach(() => {
    vi.useRealTimers();
  });

  it("stays at 00:00 while not running", () => {
    const { result } = renderHook(() => useElapsedTime(false));
    expect(result.current).toBe("00:00");
    act(() => {
      vi.advanceTimersByTime(5000);
    });
    expect(result.current).toBe("00:00");
  });

  it("counts seconds up once running", () => {
    const { result } = renderHook(({ running }) => useElapsedTime(running), {
      initialProps: { running: true },
    });
    expect(result.current).toBe("00:00");
    act(() => {
      vi.advanceTimersByTime(3000);
    });
    expect(result.current).toBe("00:03");
  });

  it("formats minutes and seconds with zero padding", () => {
    const { result } = renderHook(() => useElapsedTime(true));
    act(() => {
      vi.advanceTimersByTime(65_000);
    });
    expect(result.current).toBe("01:05");
  });

  it("resets back to 00:00 when it stops running", () => {
    const { result, rerender } = renderHook(({ running }) => useElapsedTime(running), {
      initialProps: { running: true },
    });
    act(() => {
      vi.advanceTimersByTime(4000);
    });
    expect(result.current).toBe("00:04");
    rerender({ running: false });
    expect(result.current).toBe("00:00");
  });
});
