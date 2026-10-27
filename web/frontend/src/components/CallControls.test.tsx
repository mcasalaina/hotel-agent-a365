import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";
import { CallControls } from "./CallControls";

describe("CallControls", () => {
  it("offers offline playback only when explicitly enabled by the backend", async () => {
    const onStartCall = vi.fn();
    const user = userEvent.setup();
    render(
      <CallControls
        phase="idle"
        mode={null}
        micMuted={false}
        features={{
          voiceEnabled: true,
          textEnabled: true,
          offlinePlaybackEnabled: true,
          prerecordedAudioEnabled: true,
        }}
        onStartCall={onStartCall}
        onStartPrerecorded={vi.fn()}
        onToggleMute={vi.fn()}
        onBargeIn={vi.fn()}
        onEndCall={vi.fn()}
      />,
    );

    await user.click(screen.getByRole("button", { name: /start voice call/i }));
    expect(onStartCall).toHaveBeenCalledWith("voice");

    await user.click(screen.getByRole("button", { name: /run offline walkthrough/i }));
    expect(onStartCall).toHaveBeenCalledWith("headless");
  });

  it("disables a start button when the backend reports the feature is unavailable", () => {
    render(
      <CallControls
        phase="idle"
        mode={null}
        micMuted={false}
        features={{
          voiceEnabled: false,
          textEnabled: true,
          offlinePlaybackEnabled: false,
          prerecordedAudioEnabled: true,
        }}
        onStartCall={vi.fn()}
        onStartPrerecorded={vi.fn()}
        onToggleMute={vi.fn()}
        onBargeIn={vi.fn()}
        onEndCall={vi.fn()}
      />,
    );
    expect(screen.getByRole("button", { name: /start voice call/i })).toBeDisabled();
    expect(screen.getByRole("button", { name: /start text call/i })).toBeEnabled();
    expect(screen.queryByRole("button", { name: /run offline walkthrough/i })).not.toBeInTheDocument();
  });

  it("shows mute, interrupt, and end-call controls only for a live voice call", async () => {
    const onToggleMute = vi.fn();
    const onBargeIn = vi.fn();
    const onEndCall = vi.fn();
    const user = userEvent.setup();
    render(
      <CallControls
        phase="active"
        mode="voice"
        micMuted={false}
        features={null}
        onStartCall={vi.fn()}
        onStartPrerecorded={vi.fn()}
        onToggleMute={onToggleMute}
        onBargeIn={onBargeIn}
        onEndCall={onEndCall}
      />,
    );

    await user.click(screen.getByRole("button", { name: /mute microphone/i }));
    expect(onToggleMute).toHaveBeenCalled();

    await user.click(screen.getByRole("button", { name: /interrupt agent/i }));
    expect(onBargeIn).toHaveBeenCalled();

    await user.click(screen.getByRole("button", { name: /end call/i }));
    expect(onEndCall).toHaveBeenCalled();
  });

  it("hides the mute control in text mode since there is no microphone", () => {
    render(
      <CallControls
        phase="active"
        mode="text"
        micMuted={false}
        features={null}
        onStartCall={vi.fn()}
        onStartPrerecorded={vi.fn()}
        onToggleMute={vi.fn()}
        onBargeIn={vi.fn()}
        onEndCall={vi.fn()}
      />,
    );
    expect(screen.queryByRole("button", { name: /mute microphone/i })).not.toBeInTheDocument();
  });

  it("accepts a prerecorded WAV prompt", async () => {
    const onStartPrerecorded = vi.fn();
    const user = userEvent.setup();
    render(
      <CallControls
        phase="idle"
        mode={null}
        micMuted={false}
        features={null}
        onStartCall={vi.fn()}
        onStartPrerecorded={onStartPrerecorded}
        onToggleMute={vi.fn()}
        onBargeIn={vi.fn()}
        onEndCall={vi.fn()}
      />,
    );

    const file = new File([new ArrayBuffer(44)], "spanish-prompt.wav", {
      type: "audio/wav",
    });
    await user.upload(screen.getByLabelText(/upload prerecorded wav/i), file);

    expect(onStartPrerecorded).toHaveBeenCalledWith(file);
  });
});
