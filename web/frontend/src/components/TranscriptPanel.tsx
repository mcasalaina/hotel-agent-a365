import { useEffect, useRef } from "react";
import styles from "./TranscriptPanel.module.css";
import type { TranscriptEntry } from "../hooks/callSessionReducer";

interface TranscriptPanelProps {
  transcripts: TranscriptEntry[];
}

/** Live user/agent transcript. Uses `aria-live="polite"` so screen reader users hear new turns
 * as they arrive without interrupting whatever they are currently doing. */
export function TranscriptPanel({ transcripts }: TranscriptPanelProps) {
  const listRef = useRef<HTMLDivElement | null>(null);

  useEffect(() => {
    const node = listRef.current;
    if (node) {
      node.scrollTop = node.scrollHeight;
    }
  }, [transcripts]);

  return (
    <section className={styles.panel} aria-labelledby="transcript-heading">
      <h2 className={styles.heading} id="transcript-heading">
        Live transcript
      </h2>
      <div className={styles.list} ref={listRef} aria-live="polite" aria-relevant="additions">
        {transcripts.length === 0 ? (
          <p className={styles.empty}>Transcript will appear here once the call starts.</p>
        ) : (
          transcripts.map((entry) => (
            <div
              key={entry.id}
              className={`${styles.entry} ${entry.speaker === "user" ? styles.entryUser : styles.entryAgent}`}
            >
              <span className={styles.entryMeta}>{entry.speaker === "user" ? "You" : "Agent"}</span>
              <span className={entry.isFinal ? undefined : styles.entryPartial}>{entry.text}</span>
            </div>
          ))
        )}
      </div>
    </section>
  );
}
