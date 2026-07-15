import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";
import { CallControls } from "./CallControls";

describe("CallControls", () => {
  it("offers voice, text, and headless-demo start buttons before a call begins", async () => {
    const onStartCall = vi.fn();
    const user = userEvent.setup();
    render(
      <CallControls
        phase="idle"
        mode={null}
        micMuted={false}
        features={null}
        onStartCall={onStartCall}
        onToggleMute={vi.fn()}
        onBargeIn={vi.fn()}
        onEndCall={vi.fn()}
      />,
    );

    await user.click(screen.getByRole("button", { name: /start voice call/i }));
    expect(onStartCall).toHaveBeenCalledWith("voice");

    await user.click(screen.getByRole("button", { name: /run headless demo/i }));
    expect(onStartCall).toHaveBeenCalledWith("headless");
  });

  it("disables a start button when the backend reports the feature is unavailable", () => {
    render(
      <CallControls
        phase="idle"
        mode={null}
        micMuted={false}
        features={{ voiceEnabled: false, textEnabled: true, headlessDemoEnabled: true }}
        onStartCall={vi.fn()}
        onToggleMute={vi.fn()}
        onBargeIn={vi.fn()}
        onEndCall={vi.fn()}
      />,
    );
    expect(screen.getByRole("button", { name: /start voice call/i })).toBeDisabled();
    expect(screen.getByRole("button", { name: /start text call/i })).toBeEnabled();
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
        onToggleMute={vi.fn()}
        onBargeIn={vi.fn()}
        onEndCall={vi.fn()}
      />,
    );
    expect(screen.queryByRole("button", { name: /mute microphone/i })).not.toBeInTheDocument();
  });
});
