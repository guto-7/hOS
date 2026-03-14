import { useCallback } from "react";
import type { DiagnosticNode } from "../features/diagnosticTree/types";
import { canAddChild, isDescendant } from "../features/diagnosticTree/treeUtils";

interface UseTreeActionsOptions {
  nodes: DiagnosticNode[];
  setNodes: React.Dispatch<React.SetStateAction<DiagnosticNode[]>>;
  activeNodeId: string;
  setActiveNodeId: React.Dispatch<React.SetStateAction<string>>;
}

export function useTreeActions({
  nodes,
  setNodes,
  activeNodeId,
  setActiveNodeId,
}: UseTreeActionsOptions) {
  const addDiagnosticNode = useCallback(
    (
      parentId: string,
      title: string,
      category?: string
    ): DiagnosticNode | null => {
      if (!canAddChild(parentId, nodes)) return null;

      const parent = nodes.find((n) => n.id === parentId);
      const nodeType: DiagnosticNode["nodeType"] =
        !parent || parent.nodeType === "orchestrator"
          ? "diagnostic"
          : "sub-diagnostic";

      const newNode: DiagnosticNode = {
        id: Date.now().toString(),
        title,
        titleSource: "manual",
        parentId,
        nodeType,
        diagnosticCategory: category,
        createdAt: Date.now(),
      };

      setNodes((prev) => [...prev, newNode]);
      return newNode;
    },
    [nodes, setNodes]
  );

  const addNodeWithChildren = useCallback(
    (
      parentId: string,
      title: string,
      category: string,
      childTitles: string[]
    ) => {
      if (!canAddChild(parentId, nodes)) return;

      const parent = nodes.find((n) => n.id === parentId);
      const nodeType: DiagnosticNode["nodeType"] =
        !parent || parent.nodeType === "orchestrator"
          ? "diagnostic"
          : "sub-diagnostic";

      const now = Date.now();
      const parentNode: DiagnosticNode = {
        id: now.toString(),
        title,
        titleSource: "manual",
        parentId,
        nodeType,
        diagnosticCategory: category,
        createdAt: now,
      };

      const children: DiagnosticNode[] = childTitles.map((t, i) => ({
        id: (now + i + 1).toString(),
        title: t,
        titleSource: "auto" as const,
        parentId: parentNode.id,
        nodeType: "sub-diagnostic" as const,
        diagnosticCategory: category,
        createdAt: now + i + 1,
      }));

      setNodes((prev) => [...prev, parentNode, ...children]);
      setActiveNodeId(parentNode.id);
    },
    [nodes, setNodes, setActiveNodeId]
  );

  const removeNode = useCallback(
    (nodeId: string, reparentChildren = false) => {
      const node = nodes.find((n) => n.id === nodeId);
      if (!node || node.parentId === null) return; // Can't delete root

      if (reparentChildren) {
        setNodes((prev) =>
          prev
            .map((n) =>
              n.parentId === nodeId ? { ...n, parentId: node.parentId } : n
            )
            .filter((n) => n.id !== nodeId)
        );
      } else {
        // Delete node and all descendants
        const toDelete = new Set<string>();
        function markDescendants(id: string) {
          toDelete.add(id);
          nodes.filter((n) => n.parentId === id).forEach((n) => markDescendants(n.id));
        }
        markDescendants(nodeId);
        setNodes((prev) => prev.filter((n) => !toDelete.has(n.id)));
      }

      if (activeNodeId === nodeId || isDescendant(nodeId, activeNodeId, nodes)) {
        setActiveNodeId(node.parentId!);
      }
    },
    [nodes, setNodes, activeNodeId, setActiveNodeId]
  );

  const renameNode = useCallback(
    (nodeId: string, newTitle: string) => {
      setNodes((prev) =>
        prev.map((n) =>
          n.id === nodeId
            ? { ...n, title: newTitle, titleSource: "manual" as const }
            : n
        )
      );
    },
    [setNodes]
  );

  const moveNode = useCallback(
    (nodeId: string, newParentId: string) => {
      const node = nodes.find((n) => n.id === nodeId);
      if (!node) return;
      if (node.parentId === newParentId) return; // No-op
      if (isDescendant(nodeId, newParentId, nodes)) return; // Cycle prevention
      if (nodeId === newParentId) return;
      if (!canAddChild(newParentId, nodes)) return;

      setNodes((prev) =>
        prev.map((n) =>
          n.id === nodeId ? { ...n, parentId: newParentId } : n
        )
      );
    },
    [nodes, setNodes]
  );

  return {
    addDiagnosticNode,
    addNodeWithChildren,
    removeNode,
    renameNode,
    moveNode,
  };
}
