import { useState, useRef, useCallback, useEffect } from "react";
import { getNode, type HistoryEntry } from "../../nodes/registry";
import styles from "./Dashboard.module.css";

interface DashboardProps {
  activeNodeId: string;
}

function Dashboard({ activeNodeId }: DashboardProps) {
  const node = getNode(activeNodeId);
  const [historyEntries, setHistoryEntries] = useState<HistoryEntry[]>([]);
  const [historyOpen, setHistoryOpen] = useState(false);
  const [activeLabel, setActiveLabel] = useState<string | null>(null);
  const historyLoadRef = useRef<((id: string) => void) | null>(null);
  const deleteRef = useRef<((id: string) => Promise<void>) | null>(null);
  const resetRef = useRef<(() => void) | null>(null);
  const importRef = useRef<(() => void) | null>(null);
  const dropdownRef = useRef<HTMLDivElement>(null);

  const handleHistoryChange = useCallback((entries: HistoryEntry[]) => {
    setHistoryEntries(entries);
  }, []);

  const handleHistorySelect = useCallback((id: string) => {
    historyLoadRef.current?.(id);
    setHistoryOpen(false);
  }, []);

  const handleHistoryDelete = useCallback(async (e: React.MouseEvent, id: string) => {
    e.stopPropagation();
    await deleteRef.current?.(id);
  }, []);

  const handleImport = useCallback(() => {
    importRef.current?.();
    setHistoryOpen(false);
  }, []);

  // Close dropdown on outside click
  useEffect(() => {
    if (!historyOpen) return;
    const handleClick = (e: MouseEvent) => {
      if (dropdownRef.current && !dropdownRef.current.contains(e.target as Node)) {
        setHistoryOpen(false);
      }
    };
    document.addEventListener("mousedown", handleClick);
    return () => document.removeEventListener("mousedown", handleClick);
  }, [historyOpen]);

  // Reset state when switching nodes
  useEffect(() => {
    setHistoryEntries([]);
    setHistoryOpen(false);
    setActiveLabel(null);
  }, [activeNodeId]);

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
      <div className={styles.toolbar}>
        <div className={styles.historyDropdown} ref={dropdownRef}>
          <button
            className={styles.historyButton}
            onClick={historyEntries.length > 0 ? () => setHistoryOpen(!historyOpen) : handleImport}
          >
            {historyEntries.length > 0 ? (
              <>
                {activeLabel ?? historyEntries.length}
                <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                  <polyline points="6 9 12 15 18 9" />
                </svg>
              </>
            ) : (
              <>
                <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                  <path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4" />
                  <polyline points="17 8 12 3 7 8" />
                  <line x1="12" y1="3" x2="12" y2="15" />
                </svg>
                Import
              </>
            )}
          </button>
          {historyOpen && historyEntries.length > 0 && (
            <div className={styles.historyMenu}>
              <div className={styles.historyMenuHeader}>Past Imports</div>
              {historyEntries.map((entry) => (
                <div key={entry.id} className={styles.historyMenuItem}>
                  <button
                    className={styles.historyItemContent}
                    onClick={() => handleHistorySelect(entry.id)}
                  >
                    <span className={styles.historyItemLabel}>{entry.label}</span>
                    <span className={styles.historyItemDetail}>{entry.detail}</span>
                  </button>
                  <button
                    className={styles.historyDeleteBtn}
                    onClick={(e) => handleHistoryDelete(e, entry.id)}
                    title="Delete"
                  >
                    <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                      <line x1="18" y1="6" x2="6" y2="18" />
                      <line x1="6" y1="6" x2="18" y2="18" />
                    </svg>
                  </button>
                </div>
              ))}
              <button className={styles.uploadNewBtn} onClick={handleImport}>
                <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                  <line x1="12" y1="5" x2="12" y2="19" />
                  <line x1="5" y1="12" x2="19" y2="12" />
                </svg>
                Import new
              </button>
            </div>
          )}
        </div>
      </div>
      <DashboardContent
        onHistoryChange={handleHistoryChange}
        onActiveLabel={setActiveLabel}
        historyRef={historyLoadRef}
        deleteRef={deleteRef}
        resetRef={resetRef}
        importRef={importRef}
      />
    </div>
  );
}

export default Dashboard;
