import { useState, useRef, useMemo, useEffect, useCallback } from "react";
import { NODES } from "../../nodes/registry";
import styles from "./Navigation.module.css";

interface NavigationProps {
  activeNodeId: string;
  onNodeChange: (nodeId: string) => void;
}

function Navigation({ activeNodeId, onNodeChange }: NavigationProps) {
  const containerRef = useRef<HTMLDivElement>(null);
  const [size, setSize] = useState({ w: 0, h: 0 });
  const [hoveredNodeId, setHoveredNodeId] = useState<string | null>(null);

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

  const diagnosticNodes = NODES.filter((n) => n.id !== "orchestrator");
  const cx = size.w / 2;
  const cy = size.h / 2;
  const orbitRadius = Math.min(size.w, size.h) * 0.3;
  const orchestratorRadius = 17;
  const childRadius = 11;

  const childPositions = useMemo(() => {
    const startAngle = -Math.PI / 2;
    return diagnosticNodes.map((node, i) => {
      const angle = startAngle + (2 * Math.PI * i) / diagnosticNodes.length;
      return {
        node,
        x: cx + orbitRadius * Math.cos(angle),
        y: cy + orbitRadius * Math.sin(angle),
      };
    });
  }, [cx, cy, orbitRadius, diagnosticNodes.length]);

  const selectNode = useCallback((id: string) => onNodeChange(id), [onNodeChange]);

  return (
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

          {/* Diagnostic nodes */}
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

          {/* Orchestrator (center) */}
          <circle
            cx={cx}
            cy={cy}
            r={orchestratorRadius}
            className={`${styles.node} ${styles.nodeOrchestrator} ${"orchestrator" === activeNodeId ? styles.nodeActive : ""} ${"orchestrator" === hoveredNodeId ? styles.nodeHovered : ""}`}
            onClick={() => selectNode("orchestrator")}
            onPointerEnter={() => setHoveredNodeId("orchestrator")}
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
  );
}

export default Navigation;
