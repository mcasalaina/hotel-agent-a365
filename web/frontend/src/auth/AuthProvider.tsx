/**
 * React auth context wrapping a single MSAL `PublicClientApplication`. All Entra tokens returned
 * by MSAL stay inside MSAL's in-memory cache (see `msalConfig.ts`) and inside this React state;
 * nothing here writes to localStorage, sessionStorage, or cookies.
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
import {
  AuthContext,
  type AuthContextValue,
  type AuthStatus,
  type SignedInUser,
} from "./authContext";
import { apiLoginScopes, getMsalInstance } from "./msalConfig";

function toSignedInUser(account: AccountInfo): SignedInUser {
  return {
    displayName: account.name ?? account.username,
    username: account.username,
    tenantId: account.tenantId,
  };
}

export function AuthProvider({ children }: { children: ReactNode }) {
  const msal = useMemo(() => getMsalInstance(), []);
  const [status, setStatus] = useState<AuthStatus>("initializing");
  const [user, setUser] = useState<SignedInUser | null>(null);
  const [errorMessage, setErrorMessage] = useState<string | null>(null);
  const initialized = useRef(false);

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

  const signIn = useCallback(async () => {
    setErrorMessage(null);
    setStatus("signing_in");
    try {
      const result = await msal.loginPopup({ scopes: apiLoginScopes() });
      msal.setActiveAccount(result.account);
      setUser(toSignedInUser(result.account));
      setStatus("signed_in");
    } catch (err) {
      setErrorMessage(err instanceof Error ? err.message : "Sign-in failed.");
      setStatus("signed_out");
    }
  }, [msal]);

  const signOut = useCallback(async () => {
    const account = msal.getActiveAccount();
    setUser(null);
    setStatus("signed_out");
    await msal.logoutPopup({ account: account ?? undefined }).catch(() => {
      // The user may have already closed the popup; local state is already cleared above.
    });
  }, [msal]);

  const acquireApiToken = useCallback(async (): Promise<string> => {
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
        const result = await msal.acquireTokenPopup(request);
        return result.accessToken;
      }
      throw err;
    }
  }, [msal]);

  const value = useMemo<AuthContextValue>(
    () => ({ status, user, errorMessage, signIn, signOut, acquireApiToken }),
    [status, user, errorMessage, signIn, signOut, acquireApiToken],
  );

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
}
