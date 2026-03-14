import { useState, useRef, useMemo, useCallback, useEffect } from "react";
import type { DiagnosticNode } from "./types";
import styles from "./DiagnosticTreePanel.module.css";

const CORE_NODES: DiagnosticNode[] = [
  {
    id: "root",
    title: "Medical Orchestrator",
    parentId: null,
    nodeType: "orchestrator",
    diagnosticCategory: "orchestrator",
    createdAt: 0,
  },
  {
    id: "bloodwork",
    title: "Blood Work",
    parentId: "root",
    nodeType: "diagnostic",
    diagnosticCategory: "hematology",
    createdAt: 1,
  },
  {
    id: "radiology",
    title: "Radiology",
    parentId: "root",
    nodeType: "diagnostic",
    diagnosticCategory: "imaging",
    createdAt: 2,
  },
  {
    id: "body-composition",
    title: "Body Composition",
    parentId: "root",
    nodeType: "diagnostic",
    diagnosticCategory: "anthropometry",
    createdAt: 3,
  },
];

function DiagnosticTreePanel() {
  const [activeNodeId, setActiveNodeId] = useState("root");
  const [hoveredNodeId, setHoveredNodeId] = useState<string | null>(null);
  const containerRef = useRef<HTMLDivElement>(null);
  const [size, setSize] = useState({ w: 0, h: 0 });

  // Observe container size
  useEffect(() => {
    const el = containerRef.current;
    if (!el) return;
    const ro = new ResizeObserver(([entry]) => {
      const { width, height } = entry.contentRect;
      setSize({ w: width, h: height });
    });
    ro.observe(el);
    return () => ro.disconnect();
  }, []);

  const children = CORE_NODES.filter((n) => n.parentId === "root");

  // Radial layout: orchestrator at center, children evenly spaced in a circle
  const cx = size.w / 2;
  const cy = size.h / 2;
  const orbitRadius = Math.min(size.w, size.h) * 0.3;
  const orchestratorRadius = 17;
  const childRadius = 11;

  const childPositions = useMemo(() => {
    const startAngle = -Math.PI / 2; // top
    return children.map((node, i) => {
      const angle = startAngle + (2 * Math.PI * i) / children.length;
      return {
        node,
        x: cx + orbitRadius * Math.cos(angle),
        y: cy + orbitRadius * Math.sin(angle),
      };
    });
  }, [cx, cy, orbitRadius, children.length]);

  const selectNode = useCallback((id: string) => setActiveNodeId(id), []);

  const activeNode = CORE_NODES.find((n) => n.id === activeNodeId);

  return (
    <div className={styles.panel}>
      <div ref={containerRef} className={styles.viewport}>
        {size.w > 0 && (
          <svg className={styles.canvasSvg} width={size.w} height={size.h}>
            {/* Edges */}
            {childPositions.map(({ node, x, y }) => (
              <line
                key={`edge-${node.id}`}
                x1={cx}
                y1={cy}
                x2={x}
                y2={y}
                className={styles.edge}
              />
            ))}

            {/* Child nodes */}
            {childPositions.map(({ node, x, y }) => (
              <circle
                key={node.id}
                cx={x}
                cy={y}
                r={childRadius}
                className={`${styles.node} ${node.id === activeNodeId ? styles.nodeActive : ""} ${node.id === hoveredNodeId ? styles.nodeHovered : ""}`}
                onClick={() => selectNode(node.id)}
                onPointerEnter={() => setHoveredNodeId(node.id)}
                onPointerLeave={() => setHoveredNodeId(null)}
              />
            ))}

            {/* Orchestrator (on top) */}
            <circle
              cx={cx}
              cy={cy}
              r={orchestratorRadius}
              className={`${styles.node} ${styles.nodeOrchestrator} ${"root" === activeNodeId ? styles.nodeActive : ""} ${"root" === hoveredNodeId ? styles.nodeHovered : ""}`}
              onClick={() => selectNode("root")}
              onPointerEnter={() => setHoveredNodeId("root")}
              onPointerLeave={() => setHoveredNodeId(null)}
            />
          </svg>
        )}

        {/* Labels */}
        {size.w > 0 && (
          <div className={styles.labelLayer}>
            {childPositions.map(({ node, x, y }) => (
              <div
                key={`label-${node.id}`}
                className={styles.nodeLabel}
                style={{ left: x, top: y + childRadius + 8 }}
              >
                {node.title}
              </div>
            ))}
            <div
              className={`${styles.nodeLabel} ${styles.orchestratorLabel}`}
              style={{ left: cx, top: cy + orchestratorRadius + 10 }}
            >
              Orchestrator
            </div>
          </div>
        )}
      </div>

    </div>
  );
}

export default DiagnosticTreePanel;
