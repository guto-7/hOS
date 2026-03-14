import { getCurrentWindow } from "@tauri-apps/api/window";
import type { TabId } from "../../App";
import styles from "./TabBar.module.css";

const tabs: { id: TabId; label: string }[] = [
  { id: "data", label: "Data" },
  { id: "imaging", label: "Imaging" },
  { id: "interpretation", label: "Navigation" },
  { id: "chat", label: "Chat" },
];

interface TabBarProps {
  activeTab: TabId;
  onTabChange: (tab: TabId) => void;
}

function TabBar({ activeTab, onTabChange }: TabBarProps) {
  const handleDrag = (e: React.MouseEvent) => {
    // Only drag on left-click, and not when clicking a button
    if (e.button === 0 && (e.target as HTMLElement).tagName !== "BUTTON") {
      getCurrentWindow().startDragging();
    }
  };

  return (
    <header className={styles.titleBar} onMouseDown={handleDrag}>
      <nav className={styles.pill} role="tablist" aria-label="Main navigation">
        {tabs.map((tab) => (
          <button
            key={tab.id}
            role="tab"
            aria-selected={activeTab === tab.id}
            className={`${styles.tab} ${activeTab === tab.id ? styles.active : ""}`}
            onClick={() => onTabChange(tab.id)}
          >
            {tab.label}
          </button>
        ))}
      </nav>
    </header>
  );
}

export default TabBar;
