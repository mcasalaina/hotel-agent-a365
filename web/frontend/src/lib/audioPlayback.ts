/**
 * Agent audio playback: incoming PCM16 24 kHz mono frames from the call socket are decoded and
 * scheduled back-to-back on a dedicated AudioContext so speech plays without gaps or overlap.
 */
import { PCM_SAMPLE_RATE, pcm16ToFloat32 } from "./pcm";

export class AudioPlaybackQueue {
  private audioContext: AudioContext | null = null;
  private nextStartTime = 0;
  private activeSources = new Set<AudioBufferSourceNode>();

  private ensureContext(): AudioContext {
    if (!this.audioContext) {
      this.audioContext = new AudioContext({ sampleRate: PCM_SAMPLE_RATE });
      this.nextStartTime = this.audioContext.currentTime;
    }
    return this.audioContext;
  }

  /** Enqueues a raw PCM16 24 kHz mono frame for gapless playback. */
  enqueue(frame: ArrayBuffer): void {
    const context = this.ensureContext();
    const floatData = pcm16ToFloat32(frame);
    if (floatData.length === 0) {
      return;
    }
    const audioBuffer = context.createBuffer(1, floatData.length, PCM_SAMPLE_RATE);
    audioBuffer.copyToChannel(floatData, 0);

    const source = context.createBufferSource();
    source.buffer = audioBuffer;
    source.connect(context.destination);

    const startAt = Math.max(this.nextStartTime, context.currentTime);
    source.start(startAt);
    this.nextStartTime = startAt + audioBuffer.duration;

    this.activeSources.add(source);
    source.onended = () => this.activeSources.delete(source);
  }

  /** Immediately stops and clears all queued/playing audio. Used on barge-in and call end. This
   * only affects local playback; it does not roll back any business action already committed by
   * the backend. */
  clear(): void {
    for (const source of this.activeSources) {
      try {
        source.stop();
      } catch {
        // Already stopped; ignore.
      }
    }
    this.activeSources.clear();
    if (this.audioContext) {
      this.nextStartTime = this.audioContext.currentTime;
    }
  }

  /** Releases the AudioContext entirely. Call when the call ends. */
  dispose(): void {
    this.clear();
    void this.audioContext?.close();
    this.audioContext = null;
  }
}
