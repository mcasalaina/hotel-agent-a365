import { createContext, useContext } from "react";

export type AuthStatus = "initializing" | "signed_out" | "signing_in" | "signed_in" | "error";

export interface SignedInUser {
  displayName: string;
  username: string;
  tenantId: string;
}

export interface AuthContextValue {
  status: AuthStatus;
  user: SignedInUser | null;
  errorMessage: string | null;
  signIn: () => Promise<void>;
  signOut: () => Promise<void>;
  acquireApiToken: () => Promise<string>;
}

export const AuthContext = createContext<AuthContextValue | null>(null);

export function useAuth(): AuthContextValue {
  const context = useContext(AuthContext);
  if (!context) {
    throw new Error("useAuth must be used within an AuthProvider.");
  }
  return context;
}
