import { useMemo } from "react";

interface BodyDiagramProps {
  bodyPart?: string;
  className?: string;
}

/* Map body-part labels (from detector) to SVG region IDs */
const REGION_MAP: Record<string, string[]> = {
  chest: ["torso"],
  ribs: ["torso"],
  shoulder: ["shoulder-l", "shoulder-r"],
  humerus: ["upper-arm-l", "upper-arm-r"],
  elbow: ["elbow-l", "elbow-r"],
  forearm: ["forearm-l", "forearm-r"],
  wrist: ["wrist-l", "wrist-r"],
  hand: ["hand-l", "hand-r"],
  fingers: ["hand-l", "hand-r"],
  hip: ["hip-l", "hip-r"],
  pelvis: ["hip-l", "hip-r"],
  knee: ["knee-l", "knee-r"],
  leg: ["lower-leg-l", "lower-leg-r"],
  ankle: ["ankle-l", "ankle-r"],
  foot: ["foot-l", "foot-r"],
  spine: ["spine"],
};

function BodyDiagram({ bodyPart, className }: BodyDiagramProps) {
  const highlighted = useMemo(() => {
    if (!bodyPart) return new Set<string>();
    return new Set(REGION_MAP[bodyPart.toLowerCase()] ?? []);
  }, [bodyPart]);

  const fill = (id: string) =>
    highlighted.has(id) ? "var(--accent-primary)" : "var(--text-muted)";
  const opacity = (id: string) => (highlighted.has(id) ? 0.85 : 0.18);

  return (
    <svg
      viewBox="0 0 120 280"
      className={className}
      aria-label={bodyPart ? `Body diagram highlighting ${bodyPart}` : "Body diagram"}
    >
      {/* Head */}
      <circle cx="60" cy="28" r="16" fill={fill("head")} opacity={opacity("head")} />

      {/* Neck */}
      <rect x="54" y="44" width="12" height="10" rx="3" fill={fill("neck")} opacity={opacity("neck")} />

      {/* Spine (behind torso) */}
      <rect x="57" y="54" width="6" height="72" rx="2" fill={fill("spine")} opacity={opacity("spine")} />

      {/* Torso */}
      <rect x="36" y="54" width="48" height="72" rx="8" fill={fill("torso")} opacity={opacity("torso")} />

      {/* Shoulders */}
      <ellipse cx="30" cy="60" rx="10" ry="8" fill={fill("shoulder-l")} opacity={opacity("shoulder-l")} />
      <ellipse cx="90" cy="60" rx="10" ry="8" fill={fill("shoulder-r")} opacity={opacity("shoulder-r")} />

      {/* Upper Arms */}
      <rect x="14" y="66" width="14" height="34" rx="6" fill={fill("upper-arm-l")} opacity={opacity("upper-arm-l")} />
      <rect x="92" y="66" width="14" height="34" rx="6" fill={fill("upper-arm-r")} opacity={opacity("upper-arm-r")} />

      {/* Elbows */}
      <ellipse cx="21" cy="104" rx="7" ry="6" fill={fill("elbow-l")} opacity={opacity("elbow-l")} />
      <ellipse cx="99" cy="104" rx="7" ry="6" fill={fill("elbow-r")} opacity={opacity("elbow-r")} />

      {/* Forearms */}
      <rect x="15" y="108" width="12" height="32" rx="5" fill={fill("forearm-l")} opacity={opacity("forearm-l")} />
      <rect x="93" y="108" width="12" height="32" rx="5" fill={fill("forearm-r")} opacity={opacity("forearm-r")} />

      {/* Wrists */}
      <ellipse cx="21" cy="143" rx="6" ry="5" fill={fill("wrist-l")} opacity={opacity("wrist-l")} />
      <ellipse cx="99" cy="143" rx="6" ry="5" fill={fill("wrist-r")} opacity={opacity("wrist-r")} />

      {/* Hands */}
      <ellipse cx="21" cy="154" rx="7" ry="8" fill={fill("hand-l")} opacity={opacity("hand-l")} />
      <ellipse cx="99" cy="154" rx="7" ry="8" fill={fill("hand-r")} opacity={opacity("hand-r")} />

      {/* Hips */}
      <ellipse cx="44" cy="130" rx="12" ry="8" fill={fill("hip-l")} opacity={opacity("hip-l")} />
      <ellipse cx="76" cy="130" rx="12" ry="8" fill={fill("hip-r")} opacity={opacity("hip-r")} />

      {/* Upper Legs */}
      <rect x="38" y="136" width="16" height="44" rx="7" fill={fill("upper-leg-l")} opacity={opacity("upper-leg-l")} />
      <rect x="66" y="136" width="16" height="44" rx="7" fill={fill("upper-leg-r")} opacity={opacity("upper-leg-r")} />

      {/* Knees */}
      <ellipse cx="46" cy="184" rx="8" ry="7" fill={fill("knee-l")} opacity={opacity("knee-l")} />
      <ellipse cx="74" cy="184" rx="8" ry="7" fill={fill("knee-r")} opacity={opacity("knee-r")} />

      {/* Lower Legs */}
      <rect x="39" y="190" width="14" height="42" rx="6" fill={fill("lower-leg-l")} opacity={opacity("lower-leg-l")} />
      <rect x="67" y="190" width="14" height="42" rx="6" fill={fill("lower-leg-r")} opacity={opacity("lower-leg-r")} />

      {/* Ankles */}
      <ellipse cx="46" cy="235" rx="7" ry="5" fill={fill("ankle-l")} opacity={opacity("ankle-l")} />
      <ellipse cx="74" cy="235" rx="7" ry="5" fill={fill("ankle-r")} opacity={opacity("ankle-r")} />

      {/* Feet */}
      <ellipse cx="46" cy="248" rx="9" ry="8" fill={fill("foot-l")} opacity={opacity("foot-l")} />
      <ellipse cx="74" cy="248" rx="9" ry="8" fill={fill("foot-r")} opacity={opacity("foot-r")} />
    </svg>
  );
}

export default BodyDiagram;
