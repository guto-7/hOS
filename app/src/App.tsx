import { useState } from "react";
import TabBar from "./components/TabBar/TabBar";
import Disclaimer from "./components/Disclaimer/Disclaimer";
import DataTab from "./tabs/DataTab/DataTab";
import DiagnosticTreePanel from "./features/diagnosticTree/DiagnosticTreePanel";
import ChatTab from "./tabs/ChatTab/ChatTab";
import ImagingTab from "./tabs/ImagingTab/ImagingTab";
import styles from "./App.module.css";

export type TabId = "data" | "imaging" | "interpretation" | "chat";

function App() {
  const [activeTab, setActiveTab] = useState<TabId>("data");

  return (
    <div className={styles.app}>
      <TabBar activeTab={activeTab} onTabChange={setActiveTab} />
      <main
        className={`${styles.content} ${activeTab === "interpretation" ? styles.contentFull : ""}`}
        role="tabpanel"
      >
        {activeTab === "data" && <DataTab />}
        {activeTab === "imaging" && <ImagingTab />}
        {activeTab === "interpretation" && <DiagnosticTreePanel />}
        {activeTab === "chat" && <ChatTab />}
      </main>
      <Disclaimer />
    </div>
  );
}

export default App;
