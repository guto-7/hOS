import type { ComponentType } from "react";
import HepatologyContent from "./hepatology/HepatologyContent";
import RadiologyContent from "./radiology/RadiologyContent";
import AnthropometryContent from "./anthropometry/AnthropometryContent";
import OrchestratorContent from "./orchestrator/OrchestratorContent";

export interface HistoryEntry {
  id: string;
  label: string;
  detail: string;
}

export interface NodeContentProps {
  onHistoryChange?: (entries: HistoryEntry[]) => void;
  onActiveLabel?: (label: string | null) => void;
  historyRef?: React.RefObject<((id: string) => void) | null>;
  deleteRef?: React.RefObject<((id: string) => Promise<void>) | null>;
  resetRef?: React.RefObject<(() => void) | null>;
  importRef?: React.RefObject<(() => void) | null>;
}

export interface NodeDefinition {
  id: string;
  title: string;
  description: string;
  DashboardContent: ComponentType<NodeContentProps>;
}

export const NODES: NodeDefinition[] = [
  {
    id: "hepatology",
    title: "Hepatology",
    description: "Upload hepatology PDFs and track biomarkers over time.",
    DashboardContent: HepatologyContent,
  },
  {
    id: "radiology",
    title: "Radiology",
    description: "Medical image analysis with AI-powered diagnostics.",
    DashboardContent: RadiologyContent,
  },
  {
    id: "anthropometry",
    title: "Anthropometry",
    description: "BIA report parsing and anthropometric analysis.",
    DashboardContent: AnthropometryContent,
  },
  {
    id: "orchestrator",
    title: "Orchestrator",
    description: "Cross-diagnostic analysis across all nodes.",
    DashboardContent: OrchestratorContent,
  },
];

export function getNode(id: string): NodeDefinition | undefined {
  return NODES.find((n) => n.id === id);
}
