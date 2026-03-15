import { useRef, useEffect, useState } from "react";

interface BBox {
  x1: number;
  y1: number;
  x2: number;
  y2: number;
}

interface FractureCropProps {
  /** Base64-encoded annotated image (heatmap / bbox overlay) */
  imageSrc: string;
  /** Bounding boxes to crop to */
  bboxes: { bbox: BBox; label: string }[];
  className?: string;
}

const PADDING_RATIO = 0.35; // 35% padding around the bbox

/**
 * Renders cropped zoom views of each fracture bounding box
 * from the annotated scan image.
 */
function FractureCrop({ imageSrc, bboxes, className }: FractureCropProps) {
  const [crops, setCrops] = useState<{ dataUrl: string; label: string }[]>([]);
  const imgRef = useRef<HTMLImageElement | null>(null);

  useEffect(() => {
    if (bboxes.length === 0) return;

    const img = new Image();
    img.onload = () => {
      imgRef.current = img;
      const results: { dataUrl: string; label: string }[] = [];

      for (const { bbox, label } of bboxes) {
        const bw = bbox.x2 - bbox.x1;
        const bh = bbox.y2 - bbox.y1;
        const padX = bw * PADDING_RATIO;
        const padY = bh * PADDING_RATIO;

        const cx1 = Math.max(0, bbox.x1 - padX);
        const cy1 = Math.max(0, bbox.y1 - padY);
        const cx2 = Math.min(img.naturalWidth, bbox.x2 + padX);
        const cy2 = Math.min(img.naturalHeight, bbox.y2 + padY);

        const cw = cx2 - cx1;
        const ch = cy2 - cy1;

        const canvas = document.createElement("canvas");
        canvas.width = cw;
        canvas.height = ch;
        const ctx = canvas.getContext("2d");
        if (!ctx) continue;

        ctx.drawImage(img, cx1, cy1, cw, ch, 0, 0, cw, ch);
        results.push({ dataUrl: canvas.toDataURL("image/png"), label });
      }

      setCrops(results);
    };
    img.src = imageSrc;
  }, [imageSrc, bboxes]);

  if (crops.length === 0) return null;

  return (
    <div className={className}>
      {crops.map((crop, i) => (
        <div key={i} style={{ marginBottom: i < crops.length - 1 ? "var(--space-3)" : 0 }}>
          <img
            src={crop.dataUrl}
            alt={`Zoomed view of ${crop.label}`}
            style={{
              width: "100%",
              borderRadius: "var(--radius-md)",
              border: "1px solid var(--border-color)",
            }}
          />
          <p
            style={{
              fontSize: "var(--text-xs)",
              color: "var(--text-muted)",
              marginTop: "var(--space-1)",
              textAlign: "center",
            }}
          >
            {crop.label}
          </p>
        </div>
      ))}
    </div>
  );
}

export default FractureCrop;
