use crate::pipeline::types::DomainScore;

/// Normalize an individual score to 0-100 health scale based on clinical tiers.
/// Returns (normalized_score, weight) or None if not normalizable.
fn normalize_score(system: &str, score: f64) -> Option<(f64, f64)> {
    let normalized = match system {
        // Metabolic scores
        "HOMA-IR" | "HOMA-IR (Insulin Axis)" => {
            // <1.0 = 100, 1.0-2.0 = 80-60, 2.0-3.0 = 60-30, >3.0 = 30-0
            lerp_tiers(score, &[(0.0, 100.0), (1.0, 80.0), (2.0, 60.0), (3.0, 30.0), (5.0, 0.0)])
        }
        "TyG Index" => {
            lerp_tiers(score, &[(7.0, 100.0), (8.5, 70.0), (9.0, 40.0), (9.5, 10.0), (10.0, 0.0)])
        }
        "Atherogenic Index of Plasma" => {
            lerp_tiers(score, &[(-0.3, 100.0), (0.11, 75.0), (0.21, 40.0), (0.5, 0.0)])
        }
        "TG/HDL Ratio" => {
            lerp_tiers(score, &[(0.0, 100.0), (2.0, 80.0), (3.5, 40.0), (5.0, 0.0)])
        }
        "MetS Blood Score" => {
            // 0 = 100, 1 = 66, 2 = 33, 3 = 0
            lerp_tiers(score, &[(0.0, 100.0), (1.0, 66.0), (2.0, 33.0), (3.0, 0.0)])
        }
        "De Ritis Ratio" => {
            // 0.7-1.0 optimal, >2.0 bad
            if score < 0.7 {
                Some(lerp(score, 0.3, 0.7, 60.0, 90.0))
            } else if score <= 1.0 {
                Some(90.0)
            } else {
                Some(lerp_tiers(score, &[(1.0, 90.0), (1.5, 50.0), (2.0, 20.0), (3.0, 0.0)])?)
            }
        }
        "FIB-4 Index" => {
            lerp_tiers(score, &[(0.0, 100.0), (1.3, 80.0), (2.67, 30.0), (4.0, 0.0)])
        }
        "hsCRP Risk" => {
            lerp_tiers(score, &[(0.0, 100.0), (1.0, 75.0), (3.0, 35.0), (10.0, 0.0)])
        }
        "HbA1c Category" => {
            lerp_tiers(score, &[(4.0, 100.0), (5.2, 90.0), (5.7, 60.0), (6.5, 20.0), (8.0, 0.0)])
        }
        "Uric Acid Risk" => {
            // score is in mg/dL
            lerp_tiers(score, &[(2.0, 100.0), (5.0, 85.0), (5.6, 60.0), (7.0, 30.0), (9.0, 0.0)])
        }

        // Longevity scores
        "PhenoAge" => {
            // score = PhenoAge, but we want to normalize acceleration.
            // This is tricky — we'll use the raw PhenoAge value and
            // normalization happens via the interpretation. Skip for composite.
            return None;
        }
        "Allostatic Load" => {
            // 0 = 100, 9 = 0
            lerp_tiers(score, &[(0.0, 100.0), (2.0, 70.0), (4.0, 40.0), (6.0, 15.0), (9.0, 0.0)])
        }
        "Longevity Optimals" => {
            // Already 0-100
            Some(score)
        }

        // Hormonal scores
        "SPINA-GT" => {
            // 1.41-8.67 normal range
            if score < 1.41 {
                Some(lerp(score, 0.0, 1.41, 10.0, 60.0))
            } else if score <= 8.67 {
                // Map 1.41-5.0 (middle) as optimal, edges as good
                let mid = (1.41 + 8.67) / 2.0;
                let dist = (score - mid).abs() / (8.67 - 1.41) * 2.0;
                Some(100.0 - dist * 20.0)
            } else {
                Some(lerp(score, 8.67, 15.0, 60.0, 10.0).max(0.0))
            }
        }
        "SPINA-GD" => {
            if score < 20.0 {
                Some(lerp(score, 0.0, 20.0, 10.0, 60.0))
            } else if score <= 40.0 {
                let mid = 30.0;
                let dist = (score - mid).abs() / 10.0;
                Some(100.0 - dist * 20.0)
            } else {
                Some(lerp(score, 40.0, 60.0, 60.0, 10.0).max(0.0))
            }
        }
        "Jostel's TSH Index" => {
            // sTSHI: -2 to +2 normal
            let abs_val = score.abs();
            lerp_tiers(abs_val, &[(0.0, 100.0), (1.0, 85.0), (2.0, 50.0), (3.0, 15.0), (4.0, 0.0)])
        }
        "Free Androgen Index" => {
            // Context-dependent; skip for composite unless clearly abnormal
            return None;
        }
        "Vermeulen cFT" => {
            // Context-dependent; skip for composite
            return None;
        }
        "LH:FSH Ratio" => {
            // 0.5-2.0 normal
            if score < 0.5 {
                Some(lerp(score, 0.0, 0.5, 30.0, 70.0))
            } else if score <= 2.0 {
                Some(90.0)
            } else {
                Some(lerp(score, 2.0, 4.0, 70.0, 10.0).max(0.0))
            }
        }

        _ => return None,
    };

    normalized.map(|n| (n.clamp(0.0, 100.0), 1.0))
}

/// Compute composite 0-100 score for a domain from its individual DomainScores.
pub fn domain_composite(domain: &str, scores: &[DomainScore]) -> Option<DomainScore> {
    let mut total = 0.0;
    let mut weight_sum = 0.0;
    let mut components = Vec::new();

    for s in scores {
        if let Some((norm, weight)) = normalize_score(&s.system, s.score) {
            total += norm * weight;
            weight_sum += weight;
            components.push(format!("{}: {:.0}/100", s.system, norm));
        }
    }

    if weight_sum == 0.0 { return None; }
    let composite = total / weight_sum;

    let interp = match domain {
        "Metabolic" => {
            if composite >= 80.0 { "Excellent metabolic health" }
            else if composite >= 60.0 { "Good metabolic health" }
            else if composite >= 40.0 { "Fair — some metabolic markers need attention" }
            else { "Poor metabolic health — multiple markers flagged" }
        }
        "Longevity" => {
            if composite >= 80.0 { "Excellent longevity profile" }
            else if composite >= 60.0 { "Good longevity profile" }
            else if composite >= 40.0 { "Average longevity markers" }
            else { "Below average — accelerated aging indicators" }
        }
        "Hormonal" => {
            if composite >= 80.0 { "Well-balanced hormonal profile" }
            else if composite >= 60.0 { "Mostly balanced hormonal profile" }
            else if composite >= 40.0 { "Some hormonal imbalances detected" }
            else { "Significant hormonal imbalances" }
        }
        _ => "Domain composite score"
    };

    Some(DomainScore {
        domain: domain.into(),
        system: format!("{domain} Health"),
        score: composite,
        interpretation: format!("{interp} ({composite:.0}/100)"),
        components,
        version: "hOS Composite v1".into(),
    })
}

/// Linear interpolation between tiers.
/// Tiers: &[(input_value, output_score)] sorted by input ascending.
fn lerp_tiers(val: f64, tiers: &[(f64, f64)]) -> Option<f64> {
    if tiers.is_empty() { return None; }
    if val <= tiers[0].0 { return Some(tiers[0].1); }
    if val >= tiers[tiers.len() - 1].0 { return Some(tiers[tiers.len() - 1].1); }

    for window in tiers.windows(2) {
        let (x0, y0) = window[0];
        let (x1, y1) = window[1];
        if val >= x0 && val <= x1 {
            return Some(lerp(val, x0, x1, y0, y1));
        }
    }
    Some(tiers[tiers.len() - 1].1)
}

/// Simple linear interpolation.
fn lerp(val: f64, x0: f64, x1: f64, y0: f64, y1: f64) -> f64 {
    if (x1 - x0).abs() < f64::EPSILON { return y0; }
    y0 + (val - x0) * (y1 - y0) / (x1 - x0)
}
