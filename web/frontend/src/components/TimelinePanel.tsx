import { useEffect, useRef } from "react";
import styles from "./TimelinePanel.module.css";
import type { TimelineEntry } from "../hooks/callSessionReducer";

interface TimelinePanelProps {
  timeline: TimelineEntry[];
}

const CATEGORY_LABEL: Record<TimelineEntry["category"], string> = {
  progress: "Progress",
  tool: "Tool",
  data_source: "Data source",
};

const CATEGORY_CLASS: Record<TimelineEntry["category"], string> = {
  progress: "tagProgress",
  tool: "tagTool",
  data_source: "tagDataSource",
};

/** Friendly progress/tool/data-source timeline. Never shows hidden prompts, chain-of-thought, or
 * raw backend errors -- only the short, truthful status text the backend already sanitized. */
export function TimelinePanel({ timeline }: TimelinePanelProps) {
  const listRef = useRef<HTMLDivElement | null>(null);

  useEffect(() => {
    const node = listRef.current;
    if (node) {
      node.scrollTop = node.scrollHeight;
    }
  }, [timeline]);

  return (
    <section className={styles.panel} aria-labelledby="timeline-heading">
      <h2 className={styles.heading} id="timeline-heading">
        Activity timeline
      </h2>
      <div className={styles.list} ref={listRef} aria-live="polite" aria-relevant="additions">
        {timeline.length === 0 ? (
          <p className={styles.empty}>Agent activity will appear here as the call progresses.</p>
        ) : (
          timeline.map((entry) => (
            <div className={styles.item} key={entry.id}>
              <span className={`${styles.tag} ${styles[CATEGORY_CLASS[entry.category]]}`}>
                {CATEGORY_LABEL[entry.category]}
              </span>
              <span className={styles.itemText}>{entry.message}</span>
            </div>
          ))
        )}
      </div>
    </section>
  );
}
