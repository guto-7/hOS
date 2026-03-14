import type { ComponentType } from "react";
import BloodworkContent from "./bloodwork/BloodworkContent";
import RadiologyContent from "./radiology/RadiologyContent";
import AnthropometryContent from "./anthropometry/AnthropometryContent";
import OrchestratorContent from "./orchestrator/OrchestratorContent";

export interface NodeDefinition {
  id: string;
  title: string;
  description: string;
  DashboardContent: ComponentType;
}

export const NODES: NodeDefinition[] = [
  {
    id: "bloodwork",
    title: "Blood Work",
    description: "Upload bloodwork PDFs and track biomarkers over time.",
    DashboardContent: BloodworkContent,
  },
  {
    id: "radiology",
    title: "Radiology",
    description: "Medical image analysis with AI-powered diagnostics.",
    DashboardContent: RadiologyContent,
  },
  {
    id: "anthropometry",
    title: "Body Composition",
    description: "Manual measurements and body composition analysis.",
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
