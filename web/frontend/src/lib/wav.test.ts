import { describe, expect, it } from "vitest";
import { chunkPcm16, decodePcmWave } from "./wav";

function buildWave({
  sampleRate = 48_000,
  channels = 2,
  frames = 480,
}: {
  sampleRate?: number;
  channels?: number;
  frames?: number;
} = {}): ArrayBuffer {
  const dataLength = frames * channels * 2;
  const buffer = new ArrayBuffer(44 + dataLength);
  const view = new DataView(buffer);
  const writeText = (offset: number, value: string) => {
    for (let index = 0; index < value.length; index += 1) {
      view.setUint8(offset + index, value.charCodeAt(index));
    }
  };
  writeText(0, "RIFF");
  view.setUint32(4, 36 + dataLength, true);
  writeText(8, "WAVE");
  writeText(12, "fmt ");
  view.setUint32(16, 16, true);
  view.setUint16(20, 1, true);
  view.setUint16(22, channels, true);
  view.setUint32(24, sampleRate, true);
  view.setUint32(28, sampleRate * channels * 2, true);
  view.setUint16(32, channels * 2, true);
  view.setUint16(34, 16, true);
  writeText(36, "data");
  view.setUint32(40, dataLength, true);
  for (let frame = 0; frame < frames; frame += 1) {
    for (let channel = 0; channel < channels; channel += 1) {
      view.setInt16(44 + (frame * channels + channel) * 2, frame % 2 ? 8192 : -8192, true);
    }
  }
  return buffer;
}

describe("decodePcmWave", () => {
  it("downmixes stereo and resamples to 24 kHz PCM16", () => {
    const pcm = decodePcmWave(buildWave());
    expect(pcm.byteLength).toBe(240 * 2);
  });

  it("rejects compressed or malformed audio", () => {
    expect(() => decodePcmWave(new ArrayBuffer(12))).toThrow(/valid WAV/i);
  });
});

describe("chunkPcm16", () => {
  it("keeps every PCM byte when splitting a prompt", () => {
    const pcm = new ArrayBuffer(12_345);
    const chunks = chunkPcm16(pcm);
    expect(chunks.reduce((total, chunk) => total + chunk.byteLength, 0)).toBe(pcm.byteLength);
    expect(chunks.length).toBeGreaterThan(1);
  });
});
