import { getNode } from "../../nodes/registry";
import styles from "./Chat.module.css";

interface ChatProps {
  activeNodeId: string;
}

function Chat({ activeNodeId }: ChatProps) {
  const node = getNode(activeNodeId);

  return (
    <div className={styles.chat}>
      <h1 className={styles.heading}>Chat</h1>
      <p className={styles.description}>
        {node
          ? `Ask questions about your ${node.title.toLowerCase()} data.`
          : "Select a node to start a conversation."}
      </p>
    </div>
  );
}

export default Chat;
