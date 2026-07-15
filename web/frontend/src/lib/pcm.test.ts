import { describe, expect, it } from "vitest";
import {
  PCM_BYTES_PER_SAMPLE,
  PCM_SAMPLE_RATE,
  floatTo16BitPcm,
  generateSilentPcmFrame,
  pcm16ToFloat32,
  resampleFloat32,
} from "./pcm";

describe("floatTo16BitPcm / pcm16ToFloat32", () => {
  it("round-trips representative sample values", () => {
    const input = new Float32Array([0, 1, -1, 0.5, -0.5]);
    const encoded = floatTo16BitPcm(input);
    expect(encoded.byteLength).toBe(input.length * PCM_BYTES_PER_SAMPLE);

    const decoded = pcm16ToFloat32(encoded);
    for (let i = 0; i < input.length; i += 1) {
      expect(decoded[i]).toBeCloseTo(input[i], 3);
    }
  });

  it("clamps out-of-range float samples instead of overflowing", () => {
    const input = new Float32Array([2, -2]);
    const encoded = floatTo16BitPcm(input);
    const decoded = pcm16ToFloat32(encoded);
    expect(decoded[0]).toBeCloseTo(1, 3);
    expect(decoded[1]).toBeCloseTo(-1, 3);
  });
});

describe("resampleFloat32", () => {
  it("returns the same buffer when rates match", () => {
    const input = new Float32Array([0.1, 0.2, 0.3]);
    expect(resampleFloat32(input, PCM_SAMPLE_RATE, PCM_SAMPLE_RATE)).toBe(input);
  });

  it("downsamples to roughly half the length when halving the rate", () => {
    const input = new Float32Array(1000).fill(0.5);
    const output = resampleFloat32(input, 48000, 24000);
    expect(output.length).toBeCloseTo(500, -1);
  });

  it("never produces an empty buffer for non-empty input", () => {
    const input = new Float32Array([1]);
    const output = resampleFloat32(input, 44100, 24000);
    expect(output.length).toBeGreaterThan(0);
  });
});

describe("generateSilentPcmFrame", () => {
  it("produces a zeroed buffer sized for the requested duration at 24 kHz mono", () => {
    const frame = generateSilentPcmFrame(300);
    const expectedSamples = Math.round((PCM_SAMPLE_RATE * 300) / 1000);
    expect(frame.byteLength).toBe(expectedSamples * PCM_BYTES_PER_SAMPLE);

    const view = new DataView(frame);
    for (let i = 0; i < frame.byteLength; i += 2) {
      expect(view.getInt16(i, true)).toBe(0);
    }
  });

  it("defaults to a short non-zero duration", () => {
    const frame = generateSilentPcmFrame();
    expect(frame.byteLength).toBeGreaterThan(0);
  });
});
