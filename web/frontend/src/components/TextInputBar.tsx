import { useState, type FormEvent } from "react";
import styles from "./TextInputBar.module.css";

interface TextInputBarProps {
  disabled: boolean;
  onSend: (text: string) => void;
}

/** Text-input mode: lets the guest type a turn instead of (or alongside) speaking. Always
 * available so the demo can be validated without a microphone. */
export function TextInputBar({ disabled, onSend }: TextInputBarProps) {
  const [value, setValue] = useState("");

  const handleSubmit = (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    const trimmed = value.trim();
    if (!trimmed || disabled) {
      return;
    }
    onSend(trimmed);
    setValue("");
  };

  return (
    <form className={styles.form} onSubmit={handleSubmit} aria-label="Send a text message to the agent">
      <label htmlFor="text-turn-input" className="visually-hidden">
        Type a message to the agent
      </label>
      <input
        id="text-turn-input"
        className={styles.input}
        type="text"
        placeholder={"Type a message to the agent\u2026"}
        value={value}
        onChange={(event) => setValue(event.target.value)}
        disabled={disabled}
        autoComplete="off"
      />
      <button type="submit" className={styles.sendButton} disabled={disabled || value.trim().length === 0}>
        Send
      </button>
    </form>
  );
}
