import { AppHeader } from "./components/AppHeader";
import { CallControls } from "./components/CallControls";
import { CallStatusBar } from "./components/CallStatusBar";
import { ConfirmationCard } from "./components/ConfirmationCard";
import { DispositionBanner } from "./components/DispositionBanner";
import { ErrorBanner } from "./components/ErrorBanner";
import { ResultCard } from "./components/ResultCard";
import { SignInScreen } from "./components/SignInScreen";
import { TextInputBar } from "./components/TextInputBar";
import { TimelinePanel } from "./components/TimelinePanel";
import { TranscriptPanel } from "./components/TranscriptPanel";
import { useAuth } from "./auth/authContext";
import { useCallSession } from "./hooks/useCallSession";
import { useElapsedTime } from "./hooks/useElapsedTime";
import styles from "./App.module.css";

const DEFAULT_HOTEL_BRAND_NAME = "Lyrenza Hotels";
const DEFAULT_SYNTHETIC_NOTICE =
  "All guests, reservations, and folio details in this demo are synthetic.";

function ContactCenterApp() {
  const { user, signOut } = useAuth();
  const {
    state,
    config,
    configError,
    startCall,
    startPrerecorded,
    sendText,
    toggleMute,
    endCall,
    bargeIn,
    respondToConfirmation,
  } = useCallSession();

  const isCallActive = state.phase === "active" || state.phase === "reconnecting";
  const elapsedLabel = useElapsedTime(isCallActive);

  // Text input is available whenever a call is connecting/active (every mode accepts typed turns
  // in addition to speech) but not before a call has started or after it has fully ended.
  const canSendText =
    state.phase === "connecting" || state.phase === "active" || state.phase === "reconnecting";

  if (!user) {
    // AuthGate below guarantees this branch is unreachable in practice; kept for type-safety.
    return null;
  }

  return (
    <div className={styles.appShell}>
      <AppHeader
        hotelBrandName={config?.hotelBrandName ?? DEFAULT_HOTEL_BRAND_NAME}
        user={user}
        onSignOut={() => {
          void signOut();
        }}
      />
      <main className={styles.main}>
        <div className={styles.centerColumn}>
          <CallStatusBar
            phase={state.phase}
            mode={state.mode}
            elapsedLabel={elapsedLabel}
            reconnectAttempt={state.reconnectAttempt}
            micMuted={state.micMuted}
          />
          {state.errorMessage ? <ErrorBanner message={state.errorMessage} /> : null}
          {configError ? <ErrorBanner message={configError} /> : null}
          <div className={styles.transcriptRow}>
            <TranscriptPanel transcripts={state.transcripts} />
            <TimelinePanel timeline={state.timeline} />
          </div>
          {canSendText ? <TextInputBar disabled={!canSendText} onSend={sendText} /> : null}
          {state.disposition ? <DispositionBanner disposition={state.disposition} /> : null}
        </div>
        <aside className={styles.sideColumn}>
          <CallControls
            phase={state.phase}
            mode={state.mode}
            micMuted={state.micMuted}
            features={config?.features ?? null}
            onStartCall={(mode) => {
              void startCall(mode);
            }}
            onStartPrerecorded={(file) => {
              void startPrerecorded(file);
            }}
            onToggleMute={toggleMute}
            onBargeIn={bargeIn}
            onEndCall={endCall}
          />
          {state.confirmations.length > 0 || state.resultCards.length > 0 ? (
            <div className={styles.cardsStack}>
              {state.confirmations.map((confirmation) => (
                <ConfirmationCard
                  key={confirmation.id}
                  confirmation={confirmation}
                  onRespond={respondToConfirmation}
                />
              ))}
              {state.resultCards.map((card) => (
                <ResultCard key={card.id} card={card} />
              ))}
            </div>
          ) : null}
        </aside>
      </main>
      <p className={styles.syntheticFooter}>
        {config?.syntheticDataNotice ?? DEFAULT_SYNTHETIC_NOTICE}
      </p>
    </div>
  );
}

/** Gates the whole contact-center experience behind an authenticated Entra session. There is no
 * anonymous mode: signed-out and error states always render the sign-in screen. */
function AuthGate() {
  const { status, user } = useAuth();

  if (status === "signed_in" && user) {
    return <ContactCenterApp />;
  }

  if (status === "initializing") {
    return <div className={styles.loadingScreen}>Loading&hellip;</div>;
  }

  return <SignInScreen />;
}

export default function App() {
  return <AuthGate />;
}
