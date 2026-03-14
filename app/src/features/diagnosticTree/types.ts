export interface DiagnosticNode {
  id: string;
  title: string;
  titleSource?: "auto" | "manual";
  parentId: string | null;
  nodeType: "orchestrator" | "diagnostic" | "sub-diagnostic";
  diagnosticCategory?: string;
  systemPrompt?: string | null;
  createdAt: number;
  isPinned?: boolean;
  metadata?: Record<string, unknown>;
}

export interface TreeNode {
  node: DiagnosticNode;
  children: TreeNode[];
}

export interface LayoutNode {
  id: string;
  x: number;
  y: number;
  radius: number;
  depth: number;
  node: DiagnosticNode;
}
