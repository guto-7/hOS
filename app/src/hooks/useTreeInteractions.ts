import { useState, useCallback, useEffect, useRef } from "react";
import type { LayoutNode } from "../features/diagnosticTree/types";

interface Transform {
  offsetX: number;
  offsetY: number;
  scale: number;
}

const MIN_SCALE = 0.3;
const MAX_SCALE = 3.0;
const FIT_MARGIN = 40;
const PAN_OVERSHOOT = 72;

export function useTreeInteractions(
  layoutNodes: LayoutNode[],
  containerRef: React.RefObject<HTMLDivElement | null>
) {
  const [transform, setTransform] = useState<Transform>({
    offsetX: 0,
    offsetY: 0,
    scale: 1,
  });
  const isPanning = useRef(false);
  const panStart = useRef({ x: 0, y: 0 });
  const panOffset = useRef({ x: 0, y: 0 });
  const prevNodeCount = useRef(layoutNodes.length);

  const autoFit = useCallback(() => {
    const container = containerRef.current;
    if (!container || layoutNodes.length === 0) return;

    const rect = container.getBoundingClientRect();
    const maxRadius = Math.max(...layoutNodes.map((n) => n.radius), 11);

    const xs = layoutNodes.map((n) => n.x);
    const ys = layoutNodes.map((n) => n.y);
    const minX = Math.min(...xs) - maxRadius;
    const maxX = Math.max(...xs) + maxRadius;
    const minY = Math.min(...ys) - maxRadius;
    const maxY = Math.max(...ys) + maxRadius;

    const contentW = maxX - minX;
    const contentH = maxY - minY;

    if (contentW === 0 && contentH === 0) {
      setTransform({ offsetX: rect.width / 2 - xs[0], offsetY: FIT_MARGIN, scale: 1 });
      return;
    }

    const scaleX = (rect.width - FIT_MARGIN * 2) / contentW;
    const scaleY = (rect.height - FIT_MARGIN * 2) / contentH;
    const scale = Math.min(Math.max(Math.min(scaleX, scaleY), MIN_SCALE), MAX_SCALE);

    const offsetX = (rect.width - contentW * scale) / 2 - minX * scale;
    const offsetY = (rect.height - contentH * scale) / 2 - minY * scale;

    setTransform({ offsetX, offsetY, scale });
  }, [layoutNodes, containerRef]);

  // Auto-fit when tree shape changes
  useEffect(() => {
    if (layoutNodes.length !== prevNodeCount.current) {
      prevNodeCount.current = layoutNodes.length;
      autoFit();
    }
  }, [layoutNodes.length, autoFit]);

  // Initial fit
  useEffect(() => {
    autoFit();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const clampOffset = useCallback(
    (ox: number, oy: number, s: number): [number, number] => {
      const container = containerRef.current;
      if (!container || layoutNodes.length === 0) return [ox, oy];

      const rect = container.getBoundingClientRect();
      const xs = layoutNodes.map((n) => n.x * s);
      const ys = layoutNodes.map((n) => n.y * s);

      const minContentX = Math.min(...xs);
      const maxContentX = Math.max(...xs);
      const minContentY = Math.min(...ys);
      const maxContentY = Math.max(...ys);

      return [
        Math.max(-maxContentX + PAN_OVERSHOOT, Math.min(rect.width - minContentX - PAN_OVERSHOOT, ox)),
        Math.max(-maxContentY + PAN_OVERSHOOT, Math.min(rect.height - minContentY - PAN_OVERSHOOT, oy)),
      ];
    },
    [layoutNodes, containerRef]
  );

  const handlePointerDown = useCallback(
    (e: React.PointerEvent) => {
      if (e.button !== 0) return;
      isPanning.current = true;
      panStart.current = { x: e.clientX, y: e.clientY };
      panOffset.current = { x: transform.offsetX, y: transform.offsetY };
      (e.target as HTMLElement).setPointerCapture(e.pointerId);
    },
    [transform.offsetX, transform.offsetY]
  );

  const handlePointerMove = useCallback(
    (e: React.PointerEvent) => {
      if (!isPanning.current) return;
      const dx = e.clientX - panStart.current.x;
      const dy = e.clientY - panStart.current.y;
      const [cx, cy] = clampOffset(
        panOffset.current.x + dx,
        panOffset.current.y + dy,
        transform.scale
      );
      setTransform((t) => ({ ...t, offsetX: cx, offsetY: cy }));
    },
    [transform.scale, clampOffset]
  );

  const handlePointerUp = useCallback(() => {
    isPanning.current = false;
  }, []);

  const handleWheel = useCallback(
    (e: React.WheelEvent) => {
      e.preventDefault();
      const container = containerRef.current;
      if (!container) return;

      const rect = container.getBoundingClientRect();
      const cursorX = e.clientX - rect.left;
      const cursorY = e.clientY - rect.top;

      const factor = Math.exp(-e.deltaY * 0.008);
      const newScale = Math.max(
        MIN_SCALE,
        Math.min(MAX_SCALE, transform.scale * factor)
      );

      // Zoom centered on cursor
      const ratio = newScale / transform.scale;
      const newOffsetX = cursorX - (cursorX - transform.offsetX) * ratio;
      const newOffsetY = cursorY - (cursorY - transform.offsetY) * ratio;

      const [cx, cy] = clampOffset(newOffsetX, newOffsetY, newScale);
      setTransform({ offsetX: cx, offsetY: cy, scale: newScale });
    },
    [transform, containerRef, clampOffset]
  );

  return {
    transform,
    autoFit,
    handlePointerDown,
    handlePointerMove,
    handlePointerUp,
    handleWheel,
  };
}
