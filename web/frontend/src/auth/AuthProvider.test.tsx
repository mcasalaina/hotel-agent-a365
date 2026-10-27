import { act, renderHook, waitFor } from "@testing-library/react";
import { InteractionRequiredAuthError } from "@azure/msal-browser";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { AuthProvider } from "./AuthProvider";
import { useAuth } from "./authContext";

const msal = vi.hoisted(() => ({
  initialize: vi.fn(),
  handleRedirectPromise: vi.fn(),
  getActiveAccount: vi.fn(),
  getAllAccounts: vi.fn(),
  setActiveAccount: vi.fn(),
  addEventCallback: vi.fn(),
  removeEventCallback: vi.fn(),
  loginPopup: vi.fn(),
  ssoSilent: vi.fn(),
  logoutPopup: vi.fn(),
  clearCache: vi.fn(),
  acquireTokenSilent: vi.fn(),
  acquireTokenPopup: vi.fn(),
}));

const redirect = vi.hoisted(() => ({
  isSameTabCallback: vi.fn(),
  completeSameTabSignIn: vi.fn(),
  clearStaleState: vi.fn(),
  signinRedirect: vi.fn(),
  removeUser: vi.fn(),
}));

vi.mock("./redirectAuth", () => ({
  isSameTabCallback: redirect.isSameTabCallback,
  completeSameTabSignIn: redirect.completeSameTabSignIn,
  getRedirectAuthClient: () => redirect,
}));

vi.mock("./msalConfig", () => ({
  getMsalInstance: () => msal,
  apiLoginScopes: () => ["api://hotel-api/HotelAgent.Access"],
}));

const account = {
  homeAccountId: "operator.tenant",
  localAccountId: "operator",
  environment: "login.microsoftonline.com",
  tenantId: "tenant",
  username: "operator@example.com",
  name: "Hotel Operator",
};

async function initializedProvider() {
  const hook = renderHook(() => useAuth(), { wrapper: AuthProvider });
  await waitFor(() => expect(hook.result.current.status).toBe("signed_out"));
  return hook;
}

describe("AuthProvider", () => {
  beforeEach(() => {
    vi.resetAllMocks();
    msal.initialize.mockResolvedValue(undefined);
    msal.handleRedirectPromise.mockResolvedValue(null);
    msal.getActiveAccount.mockReturnValue(null);
    msal.getAllAccounts.mockReturnValue([]);
    msal.addEventCallback.mockReturnValue("callback");
    msal.setActiveAccount.mockImplementation((next) => {
      msal.getActiveAccount.mockReturnValue(next);
    });
    msal.loginPopup.mockResolvedValue({ account, accessToken: "api-token" });
    msal.ssoSilent.mockResolvedValue({ account, accessToken: "api-token" });
    msal.logoutPopup.mockResolvedValue(undefined);
    msal.clearCache.mockResolvedValue(undefined);
    msal.acquireTokenSilent.mockResolvedValue({ accessToken: "api-token" });
    msal.acquireTokenPopup.mockResolvedValue({ accessToken: "renewed-token" });
    redirect.isSameTabCallback.mockReturnValue(false);
    redirect.clearStaleState.mockResolvedValue(undefined);
    redirect.signinRedirect.mockResolvedValue(undefined);
    redirect.removeUser.mockResolvedValue(undefined);
  });

  it("preserves interactive sign-in when no existing-session hint is requested", async () => {
    const { result } = await initializedProvider();
    await act(() => result.current.signIn());
    expect(msal.loginPopup).toHaveBeenCalledWith({
      scopes: ["api://hotel-api/HotelAgent.Access"],
    });
    expect(msal.ssoSilent).not.toHaveBeenCalled();
    expect(result.current.status).toBe("signed_in");
  });

  it("uses the explicitly selected existing account without opening a popup", async () => {
    const { result } = await initializedProvider();
    await act(() => result.current.signIn("  operator@example.com  "));
    expect(msal.ssoSilent).toHaveBeenCalledWith({
      scopes: ["api://hotel-api/HotelAgent.Access"],
      loginHint: "operator@example.com",
    });
    expect(msal.loginPopup).not.toHaveBeenCalled();
    expect(result.current.user?.username).toBe("operator@example.com");
    expect(result.current.status).toBe("signed_in");
  });

  it("surfaces silent SSO failure without falling back to interactive sign-in", async () => {
    msal.ssoSilent.mockRejectedValue(
      new InteractionRequiredAuthError("interaction_required", "Sign-in interaction required"),
    );
    const { result } = await initializedProvider();
    await act(() => result.current.signIn("operator@example.com"));
    expect(result.current.status).toBe("signed_out");
    expect(result.current.errorMessage).toContain("interaction_required");
    expect(result.current.user).toBeNull();
    expect(msal.loginPopup).not.toHaveBeenCalled();
  });

  it("surfaces required token interaction without a popup for existing-session sign-in", async () => {
    const { result } = await initializedProvider();
    await act(() => result.current.signIn("operator@example.com"));
    msal.acquireTokenSilent.mockRejectedValue(
      new InteractionRequiredAuthError("login_required", "Sign-in required"),
    );
    await expect(result.current.acquireApiToken()).rejects.toThrow(
      "Your Microsoft session requires sign-in again",
    );
    expect(msal.acquireTokenPopup).not.toHaveBeenCalled();
  });

  it("preserves interactive token renewal for interactive sign-in", async () => {
    const { result } = await initializedProvider();
    await act(() => result.current.signIn());
    msal.acquireTokenSilent.mockRejectedValue(
      new InteractionRequiredAuthError("login_required", "Sign-in required"),
    );
    await expect(result.current.acquireApiToken()).resolves.toBe("renewed-token");
    expect(msal.acquireTokenPopup).toHaveBeenCalledWith({
      scopes: ["api://hotel-api/HotelAgent.Access"],
      account,
    });
  });

  it("clears only local app authentication for existing-session sign-out", async () => {
    const { result } = await initializedProvider();
    await act(() => result.current.signIn("operator@example.com"));
    await act(() => result.current.signOut());
    expect(msal.clearCache).toHaveBeenCalledWith({ account });
    expect(msal.logoutPopup).not.toHaveBeenCalled();
    expect(msal.getActiveAccount()).toBeNull();
    expect(result.current.status).toBe("signed_out");
    expect(result.current.user).toBeNull();
  });

  it("reports local sign-out failure instead of claiming the cache was cleared", async () => {
    const { result } = await initializedProvider();
    await act(() => result.current.signIn("operator@example.com"));
    msal.clearCache.mockRejectedValue(new Error("Cache clearing failed"));
    await act(() => result.current.signOut());
    expect(result.current.status).toBe("error");
    expect(result.current.errorMessage).toBe("Cache clearing failed");
    expect(msal.logoutPopup).not.toHaveBeenCalled();
  });

  it("starts same-tab sign-in without either MSAL interaction path", async () => {
    const { result } = await initializedProvider();
    await act(() => result.current.signInSameTab("  operator@example.com  "));
    expect(redirect.clearStaleState).toHaveBeenCalledOnce();
    expect(redirect.signinRedirect).toHaveBeenCalledWith({ login_hint: "operator@example.com" });
    expect(msal.loginPopup).not.toHaveBeenCalled();
    expect(msal.ssoSilent).not.toHaveBeenCalled();
  });

  it("surfaces same-tab navigation failure", async () => {
    redirect.signinRedirect.mockRejectedValue(new Error("Navigation failed"));
    const { result } = await initializedProvider();
    await act(() => result.current.signInSameTab());
    expect(result.current.status).toBe("signed_out");
    expect(result.current.errorMessage).toBe("Navigation failed");
  });

  it("uses the callback token and clears only local authentication on sign-out", async () => {
    redirect.isSameTabCallback.mockReturnValue(true);
    redirect.completeSameTabSignIn.mockResolvedValue({
      profile: { preferred_username: account.username, tid: account.tenantId, name: account.name },
      access_token: "redirect-token",
      expired: false,
    });
    const { result } = renderHook(() => useAuth(), { wrapper: AuthProvider });
    await waitFor(() => expect(result.current.status).toBe("signed_in"));
    expect(result.current.user?.username).toBe(account.username);
    await expect(result.current.acquireApiToken()).resolves.toBe("redirect-token");
    expect(msal.handleRedirectPromise).not.toHaveBeenCalled();
    expect(msal.acquireTokenSilent).not.toHaveBeenCalled();
    await act(() => result.current.signOut());
    expect(redirect.removeUser).toHaveBeenCalledOnce();
    expect(msal.logoutPopup).not.toHaveBeenCalled();
    expect(result.current.user).toBeNull();
    expect(result.current.status).toBe("signed_out");
  });

  it("rejects expired redirect tokens without silent renewal or popups", async () => {
    redirect.isSameTabCallback.mockReturnValue(true);
    redirect.completeSameTabSignIn.mockResolvedValue({
      profile: { preferred_username: account.username, tid: account.tenantId },
      access_token: "expired-token",
      expired: true,
    });
    const { result } = renderHook(() => useAuth(), { wrapper: AuthProvider });
    await waitFor(() => expect(result.current.status).toBe("signed_in"));
    await expect(result.current.acquireApiToken()).rejects.toThrow("sign-in expired");
    expect(msal.acquireTokenPopup).not.toHaveBeenCalled();
    expect(msal.acquireTokenSilent).not.toHaveBeenCalled();
  });

  it("reports invalid callback state without authenticating", async () => {
    redirect.isSameTabCallback.mockReturnValue(true);
    redirect.completeSameTabSignIn.mockRejectedValue(new Error("No matching state found in storage"));
    const { result } = renderHook(() => useAuth(), { wrapper: AuthProvider });
    await waitFor(() => expect(result.current.status).toBe("error"));
    expect(result.current.user).toBeNull();
    expect(result.current.errorMessage).toContain("No matching state");
  });
});
