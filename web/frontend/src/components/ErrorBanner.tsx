import styles from "./ErrorBanner.module.css";

interface ErrorBannerProps {
  message: string;
}

/** Sanitized, user-safe error surface. Never renders raw backend exceptions, stack traces, or
 * tokens -- only the short message the app itself or the backend's `error` event already
 * sanitized. Uses `aria-live="assertive"` since connection errors need immediate attention. */
export function ErrorBanner({ message }: ErrorBannerProps) {
  return (
    <div className={styles.banner} role="alert" aria-live="assertive">
      {message}
    </div>
  );
}
