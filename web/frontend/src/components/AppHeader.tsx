import styles from "./AppHeader.module.css";
import type { SignedInUser } from "../auth/authContext";
import { BrandMark } from "./BrandMark";

interface AppHeaderProps {
  hotelBrandName: string;
  user: SignedInUser;
  onSignOut: () => void;
}

export function AppHeader({ hotelBrandName, user, onSignOut }: AppHeaderProps) {
  return (
    <header className={styles.header}>
      <div className={styles.brandGroup}>
        <BrandMark className={styles.brandMark} />
        <div className={styles.brandText}>
          <span className={styles.brandName}>{hotelBrandName}</span>
        </div>
      </div>
      <div className={styles.userGroup}>
        <div className={styles.userSummary}>
          <span className={styles.userName}>{user.displayName}</span>
          <span className={styles.userDetail}>{user.username}</span>
        </div>
        <button type="button" className={styles.signOutButton} onClick={onSignOut}>
          Sign out
        </button>
      </div>
    </header>
  );
}
