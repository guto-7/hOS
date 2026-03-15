import { useState } from "react";
import { getCurrentWindow } from "@tauri-apps/api/window";
import Navigation from "./components/Navigation/Navigation";
import Dashboard from "./tabs/Dashboard/Dashboard";
import Disclaimer from "./components/Disclaimer/Disclaimer";
import { getNode } from "./nodes/registry";
import styles from "./App.module.css";

type ViewId = "dashboard" | "navigation";

const VIEWS: { id: ViewId; label: string }[] = [
  { id: "dashboard", label: "Dashboard" },
  { id: "navigation", label: "Navigation" },
];

function App() {
  const [activeNodeId, setActiveNodeId] = useState("hepatology");
  const [activeView, setActiveView] = useState<ViewId>("navigation");

  const activeNode = getNode(activeNodeId);
  const nodeTitle = activeNode?.title ?? activeNodeId;

  const handleDrag = (e: React.MouseEvent) => {
    if (e.button === 0 && (e.target as HTMLElement).tagName !== "BUTTON") {
      getCurrentWindow().startDragging();
    }
  };

  return (
    <div className={styles.app}>
      <header className={styles.titleBar} onMouseDown={handleDrag}>
        <nav className={styles.pill} role="tablist" aria-label="View navigation">
          {VIEWS.map((view) => (
            <button
              key={view.id}
              role="tab"
              aria-selected={activeView === view.id}
              className={`${styles.tab} ${activeView === view.id ? styles.tabActive : ""}`}
              onClick={() => setActiveView(view.id)}
            >
              {view.label}
            </button>
          ))}
        </nav>
        <span className={styles.nodeLabel}>{nodeTitle}</span>
      </header>
      <main className={`${styles.content} ${activeView === "navigation" ? styles.contentFull : ""}`} role="tabpanel">
        {activeView === "navigation" && (
          <Navigation activeNodeId={activeNodeId} onNodeChange={setActiveNodeId} />
        )}
        {activeView === "dashboard" && <Dashboard activeNodeId={activeNodeId} />}
      </main>
      <Disclaimer />
    </div>
  );
}

export default App;
