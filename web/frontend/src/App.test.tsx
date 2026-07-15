import { render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import App from "./App";
import { initialCallSessionState } from "./hooks/callSessionReducer";

const useAuthMock = vi.fn();
const useCallSessionMock = vi.fn();

vi.mock("./auth/authContext", () => ({
  useAuth: () => useAuthMock(),
}));

vi.mock("./hooks/useCallSession", () => ({
  useCallSession: () => useCallSessionMock(),
}));

function defaultCallSession() {
  return {
    state: initialCallSessionState,
    config: null,
    configError: null,
    startCall: vi.fn(),
    sendText: vi.fn(),
    toggleMute: vi.fn(),
    endCall: vi.fn(),
    bargeIn: vi.fn(),
    respondToConfirmation: vi.fn(),
  };
}

describe("App", () => {
  it("requires sign-in before showing any call UI", () => {
    useAuthMock.mockReturnValue({
      status: "signed_out",
      user: null,
      errorMessage: null,
      signIn: vi.fn(),
      signOut: vi.fn(),
      acquireApiToken: vi.fn(),
    });
    useCallSessionMock.mockReturnValue(defaultCallSession());

    render(<App />);

    expect(screen.getByRole("button", { name: /sign in with microsoft entra/i })).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: /start voice call/i })).not.toBeInTheDocument();
  });

  it("shows a loading state while MSAL is initializing, never the call UI", () => {
    useAuthMock.mockReturnValue({
      status: "initializing",
      user: null,
      errorMessage: null,
      signIn: vi.fn(),
      signOut: vi.fn(),
      acquireApiToken: vi.fn(),
    });
    useCallSessionMock.mockReturnValue(defaultCallSession());

    render(<App />);

    expect(screen.getByText(/loading/i)).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: /start voice call/i })).not.toBeInTheDocument();
  });

  it("shows the signed-in contact-center UI, synthetic-data notice, and call controls once authenticated", () => {
    useAuthMock.mockReturnValue({
      status: "signed_in",
      user: { displayName: "Jamie Rivera", username: "jamie@example.com", tenantId: "tenant-1" },
      errorMessage: null,
      signIn: vi.fn(),
      signOut: vi.fn(),
      acquireApiToken: vi.fn(),
    });
    useCallSessionMock.mockReturnValue(defaultCallSession());

    render(<App />);

    expect(screen.getByText("Jamie Rivera")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /start voice call/i })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /run headless demo/i })).toBeInTheDocument();
    expect(
      screen.getByText(/all guests, reservations, and folio details.*are synthetic/i),
    ).toBeInTheDocument();
  });
});
