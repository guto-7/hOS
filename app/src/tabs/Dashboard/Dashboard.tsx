import { getNode } from "../../nodes/registry";
import styles from "./Dashboard.module.css";

interface DashboardProps {
  activeNodeId: string;
}

function Dashboard({ activeNodeId }: DashboardProps) {
  const node = getNode(activeNodeId);

  if (!node) {
    return (
      <div className={styles.dashboard}>
        <p className={styles.empty}>Select a node from navigation.</p>
      </div>
    );
  }

  const { DashboardContent } = node;

  return (
    <div className={styles.dashboard}>
      <h1 className={styles.heading}>{node.title}</h1>
      <p className={styles.description}>{node.description}</p>
      <DashboardContent />
    </div>
  );
}

export default Dashboard;
