// AudioWorkletProcessor that runs on the audio rendering thread. It receives whatever sample
// rate the browser's AudioContext actually grants (browsers are not required to honor a
// requested 24 kHz hint) and forwards raw Float32 mono frames to the main thread via its port.
// Resampling to 24 kHz PCM16 happens on the main thread in src/lib/audioCapture.ts, since the
// worklet thread should stay lightweight and allocation-free.
class PcmCaptureProcessor extends AudioWorkletProcessor {
  process(inputs) {
    const input = inputs[0];
    const channel = input && input[0];
    if (channel && channel.length > 0) {
      // Copy because the underlying buffer is reused by the audio thread after this call.
      const copy = new Float32Array(channel.length);
      copy.set(channel);
      this.port.postMessage(copy, [copy.buffer]);
    }
    return true;
  }
}

registerProcessor("pcm-capture-processor", PcmCaptureProcessor);
