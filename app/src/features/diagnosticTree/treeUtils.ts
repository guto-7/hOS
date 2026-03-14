import type { DiagnosticNode, TreeNode, LayoutNode } from "./types";

const MAX_CHILDREN = 20;
const COLUMN_GAP = 30;
const LEVEL_GAP = 64;
const PADDING_X = 40;
const PADDING_Y = 40;

export function getChildren(
  nodeId: string,
  nodes: DiagnosticNode[]
): DiagnosticNode[] {
  return nodes
    .filter((n) => n.parentId === nodeId)
    .sort((a, b) => a.createdAt - b.createdAt);
}

export function getRootId(
  nodeId: string,
  nodes: DiagnosticNode[]
): string | null {
  const nodeMap = new Map(nodes.map((n) => [n.id, n]));
  let current = nodeMap.get(nodeId);
  if (!current) return null;
  while (current.parentId !== null) {
    const parent = nodeMap.get(current.parentId);
    if (!parent) return current.id;
    current = parent;
  }
  return current.id;
}

export function canAddChild(parentId: string, nodes: DiagnosticNode[]): boolean {
  return getChildren(parentId, nodes).length < MAX_CHILDREN;
}

export function buildTree(
  rootId: string,
  nodes: DiagnosticNode[]
): TreeNode | null {
  const root = nodes.find((n) => n.id === rootId);
  if (!root) return null;

  function recurse(node: DiagnosticNode): TreeNode {
    const children = getChildren(node.id, nodes);
    return {
      node,
      children: children.map(recurse),
    };
  }

  return recurse(root);
}

export function getAncestorPath(
  nodeId: string,
  nodes: DiagnosticNode[]
): DiagnosticNode[] {
  const nodeMap = new Map(nodes.map((n) => [n.id, n]));
  const path: DiagnosticNode[] = [];
  let current = nodeMap.get(nodeId);
  while (current) {
    path.unshift(current);
    if (current.parentId === null) break;
    current = nodeMap.get(current.parentId);
  }
  return path;
}

export function getSiblings(
  nodeId: string,
  nodes: DiagnosticNode[]
): DiagnosticNode[] {
  const node = nodes.find((n) => n.id === nodeId);
  if (!node || node.parentId === null) return [];
  return getChildren(node.parentId, nodes);
}

export function isDescendant(
  ancestorId: string,
  nodeId: string,
  nodes: DiagnosticNode[]
): boolean {
  const nodeMap = new Map(nodes.map((n) => [n.id, n]));
  let current = nodeMap.get(nodeId);
  while (current) {
    if (current.id === ancestorId) return true;
    if (current.parentId === null) break;
    current = nodeMap.get(current.parentId);
  }
  return false;
}

interface InternalLayoutNode {
  id: string;
  depth: number;
  x: number;
  node: DiagnosticNode;
  children: InternalLayoutNode[];
}

export function buildTreeLayout(tree: TreeNode): LayoutNode[] {
  if (!tree) return [];

  let leafCounter = 0;

  // Step 1 & 2: DFS — assign depth and leaf X positions
  function assignPositions(treeNode: TreeNode, depth: number): InternalLayoutNode {
    const internal: InternalLayoutNode = {
      id: treeNode.node.id,
      depth,
      x: 0,
      node: treeNode.node,
      children: [],
    };

    if (treeNode.children.length === 0) {
      internal.x = leafCounter;
      leafCounter++;
    } else {
      internal.children = treeNode.children.map((c) =>
        assignPositions(c, depth + 1)
      );
      // Step 3: Parent centering
      const xs = internal.children.map((c) => c.x);
      internal.x = (Math.min(...xs) + Math.max(...xs)) / 2;
    }

    return internal;
  }

  const root = assignPositions(tree, 0);

  // Step 4: Separation enforcement (3 passes)
  function collectByDepth(
    node: InternalLayoutNode,
    map: Map<number, InternalLayoutNode[]>
  ) {
    const list = map.get(node.depth) || [];
    list.push(node);
    map.set(node.depth, list);
    for (const c of node.children) collectByDepth(c, map);
  }

  function shiftSubtree(node: InternalLayoutNode, dx: number) {
    node.x += dx;
    for (const c of node.children) shiftSubtree(c, dx);
  }

  for (let pass = 0; pass < 3; pass++) {
    const depthMap = new Map<number, InternalLayoutNode[]>();
    collectByDepth(root, depthMap);

    for (const [, nodesAtDepth] of depthMap) {
      nodesAtDepth.sort((a, b) => a.x - b.x);
      for (let i = 1; i < nodesAtDepth.length; i++) {
        const gap = nodesAtDepth[i].x - nodesAtDepth[i - 1].x;
        if (gap < 1.2) {
          const shift = 1.2 - gap;
          shiftSubtree(nodesAtDepth[i], shift);
        }
      }
    }
  }

  // Step 5 & 6: Collect all nodes and compute pixel positions
  const result: LayoutNode[] = [];

  function collect(node: InternalLayoutNode) {
    const radius = Math.max(4.5, 11 - node.depth * 2);
    result.push({
      id: node.id,
      x: PADDING_X + node.x * COLUMN_GAP,
      y: PADDING_Y + node.depth * LEVEL_GAP,
      radius,
      depth: node.depth,
      node: node.node,
    });
    for (const c of node.children) collect(c);
  }

  collect(root);
  return result;
}
