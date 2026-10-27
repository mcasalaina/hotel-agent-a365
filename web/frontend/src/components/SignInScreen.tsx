/**
 * Pre-call screen. Microsoft Entra sign-in is required before any text or voice session can
 * begin; there is no anonymous mode.
 */
import { useState } from "react";
import styles from "./SignInScreen.module.css";
import { useAuth } from "../auth/authContext";
import { BrandMark } from "./BrandMark";

export function SignInScreen() {
  const { status, errorMessage, signIn, signInSameTab } = useAuth();
  const [loginHint, setLoginHint] = useState("");
  const isBusy = status === "signing_in" || status === "initializing";

  return (
    <div className={styles.container}>
      <div className={styles.card} role="main" aria-labelledby="sign-in-title">
        <div className={styles.brand}>
          <BrandMark className={styles.brandMark} />
        </div>
        <h1 className={styles.title} id="sign-in-title">
          Lyrenza Hotels Contact Center
        </h1>
        <p className={styles.subtitle}>Hotel guest services &mdash; sign-in required</p>
        <p className={styles.notice}>
          Sign in with your authorized hotel account to access guest services, reservations, and
          property information.
        </p>
        <button
          type="button"
          className={styles.signInButton}
          onClick={() => {
            void signIn();
          }}
          disabled={isBusy}
        >
          {isBusy ? "Signing in\u2026" : "Sign in with Microsoft Entra"}
        </button>
        <form
          className={styles.ssoForm}
          onSubmit={(event) => {
            event.preventDefault();
            if (loginHint.trim()) {
              void signIn(loginHint.trim());
            }
          }}
        >
          <label htmlFor="hotel-account-email">Hotel account email</label>
          <input
            id="hotel-account-email"
            className={styles.accountInput}
            type="email"
            autoComplete="username"
            value={loginHint}
            onChange={(event) => setLoginHint(event.target.value)}
            disabled={isBusy}
            required
          />
          <p className={styles.ssoHelp}>
            Already signed in to Microsoft in this browser? Connect without opening a popup.
          </p>
          <button
            type="submit"
            className={styles.signInButton}
            disabled={isBusy || !loginHint.trim()}
          >
            Use existing Microsoft session
          </button>
        </form>
        <p className={styles.ssoHelp}>If popups or silent sign-in are unavailable:</p>
        <button
          type="button"
          className={styles.signInButton}
          disabled={isBusy}
          onClick={() => void signInSameTab(loginHint.trim() || undefined)}
        >
          Sign in in this tab
        </button>
        {errorMessage ? (
          <p className={styles.errorMessage} role="alert">
            {errorMessage}
          </p>
        ) : null}
      </div>
    </div>
  );
}
