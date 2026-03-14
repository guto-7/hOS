import styles from "./Disclaimer.module.css";

function Disclaimer() {
  return (
    <footer className={styles.disclaimer}>
      <span className={styles.icon} aria-hidden="true">i</span>
      <p className={styles.text}>
        This tool is not a substitute for professional medical advice, diagnosis,
        or treatment. Always consult a qualified healthcare provider.
      </p>
    </footer>
  );
}

export default Disclaimer;
