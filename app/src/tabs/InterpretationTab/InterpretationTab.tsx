import styles from "./InterpretationTab.module.css";

function InterpretationTab() {
  return (
    <div className={styles.tab}>
      <h1 className={styles.heading}>Interpretation</h1>
      <p className={styles.description}>
        Get AI-powered analysis of your bloodwork results. Understand what your
        markers mean, how they relate to each other, and what patterns emerge
        across your test history.
      </p>
    </div>
  );
}

export default InterpretationTab;
