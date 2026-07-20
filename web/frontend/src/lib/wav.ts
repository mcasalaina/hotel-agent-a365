import { floatTo16BitPcm, PCM_BYTES_PER_SAMPLE, PCM_SAMPLE_RATE, resampleFloat32 } from "./pcm";

const RIFF_HEADER_SIZE = 12;
const PCM_FORMAT = 1;

function fourCc(view: DataView, offset: number): string {
  return String.fromCharCode(
    view.getUint8(offset),
    view.getUint8(offset + 1),
    view.getUint8(offset + 2),
    view.getUint8(offset + 3),
  );
}

/** Decodes an uncompressed 16-bit PCM WAV file and converts it to 24 kHz mono PCM16. */
export function decodePcmWave(buffer: ArrayBuffer): ArrayBuffer {
  const view = new DataView(buffer);
  if (
    view.byteLength < RIFF_HEADER_SIZE ||
    fourCc(view, 0) !== "RIFF" ||
    fourCc(view, 8) !== "WAVE"
  ) {
    throw new Error("The selected file is not a valid WAV recording.");
  }

  let channels = 0;
  let sampleRate = 0;
  let bitsPerSample = 0;
  let audioFormat = 0;
  let dataOffset = -1;
  let dataLength = 0;

  for (let offset = RIFF_HEADER_SIZE; offset + 8 <= view.byteLength; ) {
    const chunkId = fourCc(view, offset);
    const chunkLength = view.getUint32(offset + 4, true);
    const payloadOffset = offset + 8;
    if (payloadOffset + chunkLength > view.byteLength) {
      throw new Error("The WAV recording contains a truncated chunk.");
    }
    if (chunkId === "fmt " && chunkLength >= 16) {
      audioFormat = view.getUint16(payloadOffset, true);
      channels = view.getUint16(payloadOffset + 2, true);
      sampleRate = view.getUint32(payloadOffset + 4, true);
      bitsPerSample = view.getUint16(payloadOffset + 14, true);
    } else if (chunkId === "data") {
      dataOffset = payloadOffset;
      dataLength = chunkLength;
    }
    offset = payloadOffset + chunkLength + (chunkLength % 2);
  }

  if (
    audioFormat !== PCM_FORMAT ||
    bitsPerSample !== 16 ||
    ![1, 2].includes(channels) ||
    sampleRate <= 0 ||
    dataOffset < 0
  ) {
    throw new Error("Use a mono or stereo, uncompressed 16-bit PCM WAV recording.");
  }

  const frameSize = channels * PCM_BYTES_PER_SAMPLE;
  const frameCount = Math.floor(dataLength / frameSize);
  if (frameCount === 0) {
    throw new Error("The WAV recording does not contain any audio samples.");
  }
  const mono = new Float32Array(frameCount);
  for (let frame = 0; frame < frameCount; frame += 1) {
    let sum = 0;
    for (let channel = 0; channel < channels; channel += 1) {
      const sampleOffset = dataOffset + frame * frameSize + channel * PCM_BYTES_PER_SAMPLE;
      sum += view.getInt16(sampleOffset, true) / 0x8000;
    }
    mono[frame] = sum / channels;
  }
  return floatTo16BitPcm(resampleFloat32(mono, sampleRate, PCM_SAMPLE_RATE));
}

/** Splits PCM16 into small frames so browser and headless tests use the same wire cadence. */
export function chunkPcm16(
  pcm: ArrayBuffer,
  durationMs = 50,
): ArrayBuffer[] {
  const bytesPerChunk =
    Math.round((PCM_SAMPLE_RATE * durationMs) / 1000) * PCM_BYTES_PER_SAMPLE;
  const chunks: ArrayBuffer[] = [];
  for (let offset = 0; offset < pcm.byteLength; offset += bytesPerChunk) {
    chunks.push(pcm.slice(offset, Math.min(offset + bytesPerChunk, pcm.byteLength)));
  }
  return chunks;
}
