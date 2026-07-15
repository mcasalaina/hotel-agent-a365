/**
 * Pre-call screen. Microsoft Entra sign-in is required before any text or voice session can
 * begin; there is no anonymous mode.
 */
import styles from "./SignInScreen.module.css";
import { useAuth } from "../auth/authContext";

export function SignInScreen() {
  const { status, errorMessage, signIn } = useAuth();
  const isBusy = status === "signing_in" || status === "initializing";

  return (
    <div className={styles.container}>
      <div className={styles.card} role="main" aria-labelledby="sign-in-title">
        <div className={styles.brand}>
          <img className={styles.brandMark} src="/favicon.svg" alt="" aria-hidden="true" />
        </div>
        <h1 className={styles.title} id="sign-in-title">
          Lyrenza Hotels Contact Center
        </h1>
        <p className={styles.subtitle}>Simulated agent demo &mdash; sign-in required</p>
        <p className={styles.notice}>
          This is a demonstration environment. The Lyrenza Hotels brand, guests, reservations, and
          folio details shown here are entirely <strong>synthetic</strong> and do not represent a
          real hotel chain or real customer data.
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
        {errorMessage ? (
          <p className={styles.errorMessage} role="alert">
            {errorMessage}
          </p>
        ) : null}
      </div>
    </div>
  );
}
