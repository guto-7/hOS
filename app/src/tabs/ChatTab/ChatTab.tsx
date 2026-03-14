import styles from "./ChatTab.module.css";

function ChatTab() {
  return (
    <div className={styles.tab}>
      <h1 className={styles.heading}>Chat</h1>
      <p className={styles.description}>
        Ask follow-up questions about your bloodwork in a conversational
        interface. Get personalized explanations and explore your health data
        interactively.
      </p>
    </div>
  );
}

export default ChatTab;
