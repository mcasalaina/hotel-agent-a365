/**
 * Microphone capture: Web Audio API -> AudioWorklet -> resample to 24 kHz -> PCM16 mono frames.
 *
 * Requires an explicit `getUserMedia` grant. The headless/demo mode never calls this module; it
 * sends a generated silent PCM frame instead (see `pcm.ts#generateSilentPcmFrame`).
 */
import { PCM_SAMPLE_RATE, floatTo16BitPcm, resampleFloat32 } from "./pcm";

export interface AudioCaptureHandle {
  /** Stops the microphone stream and releases the AudioContext/AudioWorklet resources. */
  stop: () => void;
  /** Mutes/unmutes locally without tearing down the capture graph (frames are dropped while
   * muted rather than sent silent, to avoid misleading the backend about mic activity). */
  setMuted: (muted: boolean) => void;
}

export type PcmFrameHandler = (frame: ArrayBuffer) => void;

/** Starts microphone capture and invokes `onFrame` with PCM16 24 kHz mono frames as they become
 * available. Throws if `getUserMedia` is unavailable or permission is denied. */
export async function startAudioCapture(onFrame: PcmFrameHandler): Promise<AudioCaptureHandle> {
  if (!navigator.mediaDevices?.getUserMedia) {
    throw new Error("This browser does not support microphone capture.");
  }
  const stream = await navigator.mediaDevices.getUserMedia({
    audio: {
      channelCount: 1,
      echoCancellation: true,
      noiseSuppression: true,
      autoGainControl: true,
    },
  });

  const audioContext = new AudioContext({ sampleRate: PCM_SAMPLE_RATE });
  await audioContext.audioWorklet.addModule("/audio/pcm-capture-processor.js");

  const source = audioContext.createMediaStreamSource(stream);
  const workletNode = new AudioWorkletNode(audioContext, "pcm-capture-processor", {
    numberOfInputs: 1,
    numberOfOutputs: 0,
    channelCount: 1,
  });

  let muted = false;
  workletNode.port.onmessage = (event: MessageEvent<Float32Array<ArrayBuffer>>) => {
    if (muted) {
      return;
    }
    const resampled = resampleFloat32(event.data, audioContext.sampleRate, PCM_SAMPLE_RATE);
    onFrame(floatTo16BitPcm(resampled));
  };

  source.connect(workletNode);

  return {
    stop: () => {
      workletNode.port.onmessage = null;
      source.disconnect();
      workletNode.disconnect();
      stream.getTracks().forEach((track) => track.stop());
      void audioContext.close();
    },
    setMuted: (value: boolean) => {
      muted = value;
    },
  };
}
