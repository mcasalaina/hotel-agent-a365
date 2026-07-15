import styles from "./ResultCard.module.css";
import type { ResultCardEntry } from "../hooks/callSessionReducer";

interface ResultCardProps {
  card: ResultCardEntry;
}

const TYPE_LABEL: Record<ResultCardEntry["cardType"], string> = {
  reservation: "Reservation",
  folio: "Folio",
  request: "Request",
};

/** Renders a reservation/folio/request result card. Only the plain label/value fields the
 * backend sent are shown -- no raw system identifiers or unnecessary guest data. */
export function ResultCard({ card }: ResultCardProps) {
  return (
    <div className={styles.card} role="group" aria-label={`${TYPE_LABEL[card.cardType]} result`}>
      <div className={styles.badgeRow}>
        <span className={styles.typeBadge}>{TYPE_LABEL[card.cardType]}</span>
      </div>
      <p className={styles.title}>{card.title}</p>
      <dl className={styles.fields}>
        {Object.entries(card.fields).map(([key, value]) => (
          <div key={key} style={{ display: "contents" }}>
            <dt className={styles.fieldKey}>{key}</dt>
            <dd className={styles.fieldValue}>{value}</dd>
          </div>
        ))}
      </dl>
    </div>
  );
}
