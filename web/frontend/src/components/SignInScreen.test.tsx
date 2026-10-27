import { fireEvent, render, screen } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { SignInScreen } from "./SignInScreen";

const signIn = vi.hoisted(() => vi.fn());
const signInSameTab = vi.hoisted(() => vi.fn());

vi.mock("../auth/authContext", () => ({
  useAuth: () => ({ status: "signed_out", errorMessage: null, signIn, signInSameTab }),
}));

describe("SignInScreen", () => {
  beforeEach(() => {
    signIn.mockReset();
    signInSameTab.mockReset();
  });

  it("requires an explicit account for existing-session sign-in", () => {
    render(<SignInScreen />);
    const button = screen.getByRole("button", { name: "Use existing Microsoft session" });
    expect(button).toBeDisabled();
    fireEvent.change(screen.getByLabelText("Hotel account email"), {
      target: { value: "operator@example.com" },
    });
    fireEvent.click(button);
    expect(signIn).toHaveBeenCalledWith("operator@example.com");
  });

  it("keeps ordinary interactive sign-in available without an email hint", () => {
    render(<SignInScreen />);
    fireEvent.click(screen.getByRole("button", { name: "Sign in with Microsoft Entra" }));
    expect(signIn).toHaveBeenCalledWith();
  });

  it("uses the explicit same-tab action with the selected account", () => {
    render(<SignInScreen />);
    fireEvent.change(screen.getByLabelText("Hotel account email"), {
      target: { value: "operator@example.com" },
    });
    fireEvent.click(screen.getByRole("button", { name: "Sign in in this tab" }));
    expect(signInSameTab).toHaveBeenCalledWith("operator@example.com");
    expect(signIn).not.toHaveBeenCalled();
  });
});
