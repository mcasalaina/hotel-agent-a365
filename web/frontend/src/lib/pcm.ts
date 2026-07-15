/**
 * PCM16 mono helpers shared by capture, playback, and the headless/demo mode. The wire format
 * for both directions of the call socket's binary frames is raw signed 16-bit little-endian PCM
 * at 24 kHz mono, with no header or envelope.
 */

export const PCM_SAMPLE_RATE = 24_000;
export const PCM_BYTES_PER_SAMPLE = 2;

/** Converts a Float32 buffer in the range [-1, 1] to signed 16-bit little-endian PCM bytes. */
export function floatTo16BitPcm(input: Float32Array): ArrayBuffer {
  const output = new ArrayBuffer(input.length * PCM_BYTES_PER_SAMPLE);
  const view = new DataView(output);
  for (let i = 0; i < input.length; i += 1) {
    const clamped = Math.max(-1, Math.min(1, input[i]));
    const sample = clamped < 0 ? clamped * 0x8000 : clamped * 0x7fff;
    view.setInt16(i * PCM_BYTES_PER_SAMPLE, sample, true);
  }
  return output;
}

/** Converts signed 16-bit little-endian PCM bytes back into a Float32 buffer in [-1, 1]. */
export function pcm16ToFloat32(buffer: ArrayBuffer): Float32Array<ArrayBuffer> {
  const view = new DataView(buffer);
  const sampleCount = Math.floor(buffer.byteLength / PCM_BYTES_PER_SAMPLE);
  const output = new Float32Array(sampleCount);
  for (let i = 0; i < sampleCount; i += 1) {
    const sample = view.getInt16(i * PCM_BYTES_PER_SAMPLE, true);
    output[i] = sample < 0 ? sample / 0x8000 : sample / 0x7fff;
  }
  return output;
}

/** Linearly resamples a Float32 mono buffer from `fromRate` to `toRate`. Used to convert whatever
 * sample rate the browser's `AudioContext` actually grants into the 24 kHz the wire protocol
 * requires, since browsers are not required to honor a requested `sampleRate` hint. */
export function resampleFloat32(
  input: Float32Array<ArrayBuffer>,
  fromRate: number,
  toRate: number,
): Float32Array<ArrayBuffer> {
  if (fromRate === toRate || input.length === 0) {
    return input;
  }
  const ratio = fromRate / toRate;
  const outputLength = Math.max(1, Math.round(input.length / ratio));
  const output = new Float32Array(outputLength);
  for (let i = 0; i < outputLength; i += 1) {
    const sourceIndex = i * ratio;
    const lowIndex = Math.floor(sourceIndex);
    const highIndex = Math.min(lowIndex + 1, input.length - 1);
    const weight = sourceIndex - lowIndex;
    output[i] = input[lowIndex] * (1 - weight) + input[highIndex] * weight;
  }
  return output;
}

/** Generates a short (default 300ms) silent PCM16 24 kHz mono frame. Used by headless/demo mode
 * so the send-audio code path can be exercised end-to-end without microphone permission. */
export function generateSilentPcmFrame(durationMs = 300): ArrayBuffer {
  const sampleCount = Math.round((PCM_SAMPLE_RATE * durationMs) / 1000);
  return new ArrayBuffer(sampleCount * PCM_BYTES_PER_SAMPLE);
}
