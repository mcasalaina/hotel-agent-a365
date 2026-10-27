/**
 * Shared auth context for MSAL popup/silent sign-in and same-tab PKCE.
 * Entra tokens stay in the selected client's memory-only cache and React state.
 */
import {
  type AccountInfo,
  type AuthenticationResult,
  EventType,
  InteractionRequiredAuthError,
} from "@azure/msal-browser";
import {
  useCallback,
  useEffect,
  useMemo,
  useRef,
  useState,
  type ReactNode,
} from "react";
import type { User } from "oidc-client-ts";
import {
  AuthContext,
  type AuthContextValue,
  type AuthStatus,
  type SignedInUser,
} from "./authContext";
import { apiLoginScopes, getMsalInstance } from "./msalConfig";
import { completeSameTabSignIn, getRedirectAuthClient, isSameTabCallback } from "./redirectAuth";

function toSignedInUser(account: AccountInfo): SignedInUser {
  return {
    displayName: account.name ?? account.username,
    username: account.username,
    tenantId: account.tenantId,
  };
}

function toRedirectUser(user: User): SignedInUser {
  const { preferred_username: username, tid: tenantId, name } = user.profile;
  if (typeof username !== "string" || !username || typeof tenantId !== "string" || !tenantId) {
    throw new Error("Microsoft sign-in did not return the required account and tenant.");
  }
  return { username, tenantId, displayName: typeof name === "string" ? name : username };
}

export function AuthProvider({ children }: { children: ReactNode }) {
  const msal = useMemo(() => getMsalInstance(), []);
  const [status, setStatus] = useState<AuthStatus>("initializing");
  const [user, setUser] = useState<SignedInUser | null>(null);
  const [errorMessage, setErrorMessage] = useState<string | null>(null);
  const initialized = useRef(false);
  const silentSession = useRef(false);
  const redirectUser = useRef<User | null>(null);

  useEffect(() => {
    if (initialized.current) {
      return;
    }
    initialized.current = true;
    let cancelled = false;

    const callbackId = msal.addEventCallback((event) => {
      if (event.eventType === EventType.LOGIN_SUCCESS && event.payload) {
        const result = event.payload as AuthenticationResult;
        if (result.account) {
          msal.setActiveAccount(result.account);
        }
      }
    });

    (async () => {
      try {
        await msal.initialize();
        if (isSameTabCallback()) {
          const result = await completeSameTabSignIn();
          if (!cancelled) {
            const signedInUser = toRedirectUser(result);
            redirectUser.current = result;
            setUser(signedInUser);
            setStatus("signed_in");
          }
          return;
        }
        const redirectResult = await msal.handleRedirectPromise();
        if (cancelled) {
          return;
        }
        const account = redirectResult?.account ?? msal.getActiveAccount() ?? msal.getAllAccounts()[0];
        if (account) {
          msal.setActiveAccount(account);
          setUser(toSignedInUser(account));
          setStatus("signed_in");
        } else {
          setStatus("signed_out");
        }
      } catch (err) {
        if (!cancelled) {
          setErrorMessage(err instanceof Error ? err.message : "Sign-in failed.");
          setStatus("error");
        }
      }
    })();

    return () => {
      cancelled = true;
      if (callbackId) {
        msal.removeEventCallback(callbackId);
      }
    };
  }, [msal]);

  const signInSameTab = useCallback(async (loginHint?: string) => {
    setErrorMessage(null);
    setStatus("signing_in");
    try {
      const client = getRedirectAuthClient();
      await client.clearStaleState();
      await client.signinRedirect({ login_hint: loginHint?.trim() || undefined });
    } catch (err) {
      setErrorMessage(err instanceof Error ? err.message : "Sign-in failed.");
      setStatus("signed_out");
    }
  }, []);

  const signIn = useCallback(async (requestedLoginHint?: string) => {
    setErrorMessage(null);
    setStatus("signing_in");
    try {
      const loginHint = requestedLoginHint?.trim();
      const request = { scopes: apiLoginScopes() };
      const result = loginHint
        ? await msal.ssoSilent({ ...request, loginHint })
        : await msal.loginPopup(request);
      silentSession.current = Boolean(loginHint);
      msal.setActiveAccount(result.account);
      setUser(toSignedInUser(result.account));
      setStatus("signed_in");
    } catch (err) {
      setErrorMessage(err instanceof Error ? err.message : "Sign-in failed.");
      setStatus("signed_out");
    }
  }, [msal]);

  const signOut = useCallback(async () => {
    if (redirectUser.current) {
      try {
        await getRedirectAuthClient().removeUser();
        redirectUser.current = null;
        setErrorMessage(null);
        setUser(null);
        setStatus("signed_out");
      } catch (err) {
        setErrorMessage(err instanceof Error ? err.message : "Sign-out failed.");
        setStatus("error");
      }
      return;
    }
    const account = msal.getActiveAccount();
    if (silentSession.current) {
      try {
        await msal.clearCache({ account: account ?? undefined });
        msal.setActiveAccount(null);
        silentSession.current = false;
        setErrorMessage(null);
        setUser(null);
        setStatus("signed_out");
      } catch (err) {
        setErrorMessage(err instanceof Error ? err.message : "Sign-out failed.");
        setStatus("error");
      }
      return;
    }
    setUser(null);
    setStatus("signed_out");
    await msal.logoutPopup({ account: account ?? undefined }).catch(() => {
      // The user may have already closed the popup; local state is already cleared above.
    });
  }, [msal]);

  const acquireApiToken = useCallback(async (): Promise<string> => {
    if (redirectUser.current) {
      if (redirectUser.current.expired !== false || !redirectUser.current.access_token) {
        throw new Error("Your Microsoft sign-in expired. Sign out and sign in again in this tab.");
      }
      return redirectUser.current.access_token;
    }
    const account = msal.getActiveAccount();
    if (!account) {
      throw new Error("No signed-in account. Sign in before starting a call.");
    }
    const request = { scopes: apiLoginScopes(), account };
    try {
      const result = await msal.acquireTokenSilent(request);
      return result.accessToken;
    } catch (err) {
      if (err instanceof InteractionRequiredAuthError) {
        if (silentSession.current) {
          throw new Error(
            "Your Microsoft session requires sign-in again. Sign out of the contact center " +
              "and reconnect with your existing Microsoft session.",
            { cause: err },
          );
        }
        const result = await msal.acquireTokenPopup(request);
        return result.accessToken;
      }
      throw err;
    }
  }, [msal]);

  const value = useMemo<AuthContextValue>(
    () => ({ status, user, errorMessage, signIn, signInSameTab, signOut, acquireApiToken }),
    [status, user, errorMessage, signIn, signInSameTab, signOut, acquireApiToken],
  );

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
}
