use crate::pipeline::types::DomainScore;
use super::{MarkerLookup, UserProfile};

const DOMAIN: &str = "Hormonal";

/// SPINA-GT: Thyroid secretory capacity.
/// Formula: 0.00759 × (2.75 + TSH) × FT4 / TSH
/// Units: TSH mIU/L, FT4 pmol/L → result in pmol/s
pub fn spina_gt(m: &MarkerLookup) -> Option<DomainScore> {
    let tsh = m.val("tsh")?;
    if tsh <= 0.0 { return None; }
    let ft4 = m.val("free t4")?;

    let score = 0.00759 * (2.75 + tsh) * ft4 / tsh;

    let interp = if score < 1.41 {
        "Reduced thyroid secretory capacity (hypothyroidism pattern)"
    } else if score <= 8.67 {
        "Normal thyroid secretory capacity"
    } else {
        "Elevated thyroid secretory capacity (hyperthyroidism / autonomy)"
    };

    Some(DomainScore {
        domain: DOMAIN.into(),
        system: "SPINA-GT".into(),
        score,
        interpretation: format!("{interp} ({score:.2} pmol/s)"),
        components: vec!["TSH".into(), "Free T4".into()],
        version: "Dietrich 2016".into(),
    })
}

/// SPINA-GD: Peripheral deiodinase activity (T4→T3 conversion).
/// Formula: 0.1849 × (500 + FT4) × FT3 / FT4
/// Units: FT4 pmol/L, FT3 pmol/L → result in nmol/s
pub fn spina_gd(m: &MarkerLookup) -> Option<DomainScore> {
    let ft4 = m.val("free t4")?;
    if ft4 <= 0.0 { return None; }
    let ft3 = m.val("free t3")?;

    let score = 0.1849 * (500.0 + ft4) * ft3 / ft4;

    let interp = if score < 20.0 {
        "Low peripheral T4→T3 conversion (selenium deficiency? non-thyroidal illness?)"
    } else if score <= 40.0 {
        "Normal peripheral deiodinase activity"
    } else {
        "Enhanced peripheral T4→T3 conversion"
    };

    Some(DomainScore {
        domain: DOMAIN.into(),
        system: "SPINA-GD".into(),
        score,
        interpretation: format!("{interp} ({score:.1} nmol/s)"),
        components: vec!["Free T4".into(), "Free T3".into()],
        version: "Dietrich 2016".into(),
    })
}

/// Jostel's TSH Index: pituitary thyrotropic function.
/// TSHI = ln(TSH) + 0.1345 × FT4
/// sTSHI = (TSHI - 2.7) / 0.676
pub fn jostel_tshi(m: &MarkerLookup) -> Option<DomainScore> {
    let tsh = m.val("tsh")?;
    if tsh <= 0.0 { return None; }
    let ft4 = m.val("free t4")?;

    let tshi = tsh.ln() + 0.1345 * ft4;
    let standardised = (tshi - 2.7) / 0.676;

    let interp = if standardised < -2.0 {
        "Impaired pituitary thyrotropic function (central hypothyroidism?)"
    } else if standardised <= 2.0 {
        "Normal pituitary-thyroid axis"
    } else {
        "Enhanced thyrotropic drive"
    };

    Some(DomainScore {
        domain: DOMAIN.into(),
        system: "Jostel's TSH Index".into(),
        score: standardised,
        interpretation: format!("{interp} (sTSHI: {standardised:+.2} SD)"),
        components: vec!["TSH".into(), "Free T4".into()],
        version: "Jostel 2009".into(),
    })
}

/// Free Androgen Index: (Total Testosterone / SHBG) × 100.
/// Both in nmol/L in our canonical units — no conversion needed.
pub fn fai(m: &MarkerLookup, profile: &UserProfile) -> Option<DomainScore> {
    let tt = m.val("total testosterone")?;
    let shbg = m.val("shbg")?;
    if shbg <= 0.0 { return None; }
    let score = (tt / shbg) * 100.0;

    let is_female = profile.sex.as_deref().map(|s| s.to_lowercase())
        .map(|s| s == "female" || s == "f")
        .unwrap_or(false);

    let interp = if is_female {
        if score > 5.0 {
            "Elevated — suggestive of hyperandrogenism"
        } else if score >= 0.65 {
            "Normal female androgen index"
        } else {
            "Low androgen index"
        }
    } else {
        if score >= 24.3 && score <= 110.2 {
            "Normal male androgen index"
        } else if score < 24.3 {
            "Low androgen index — possible hypogonadism"
        } else {
            "Elevated androgen index"
        }
    };

    Some(DomainScore {
        domain: DOMAIN.into(),
        system: "Free Androgen Index".into(),
        score,
        interpretation: interp.into(),
        components: vec!["Total Testosterone".into(), "SHBG".into()],
        version: "Vermeulen 1999".into(),
    })
}

/// Vermeulen Calculated Free Testosterone.
/// Uses mass-action equilibrium with SHBG and albumin.
/// Kt = 1.0×10⁹ L/mol, Ka = 3.6×10⁴ L/mol
/// TT and SHBG in nmol/L, Albumin in g/L.
pub fn vermeulen_free_t(m: &MarkerLookup, profile: &UserProfile) -> Option<DomainScore> {
    let tt_nmol = m.val("total testosterone")?;
    let shbg_nmol = m.val("shbg")?;

    // Albumin: use measured value or default 43 g/L
    let albumin_gl = m.val("albumin").unwrap_or(43.0);

    // Convert to mol/L for the calculation
    let t = tt_nmol * 1e-9;          // nmol/L → mol/L
    let shbg = shbg_nmol * 1e-9;     // nmol/L → mol/L
    let alb = albumin_gl / 66500.0;  // g/L / MW(albumin) = mol/L

    let kt: f64 = 1.0e9;
    let ka: f64 = 3.6e4;

    let a = ka + kt + (ka * kt) * (shbg + alb - t);
    let b = 1.0 + kt * shbg + ka * alb - (ka + kt) * t;
    let discriminant = b * b + 4.0 * a * t;
    if discriminant < 0.0 || a == 0.0 { return None; }

    let ft_mol = (-b + discriminant.sqrt()) / (2.0 * a);
    let ft_pmol = ft_mol * 1e12; // mol/L → pmol/L

    let is_female = profile.sex.as_deref().map(|s| s.to_lowercase())
        .map(|s| s == "female" || s == "f")
        .unwrap_or(false);

    let interp = if is_female {
        "Calculated free testosterone (female reference ranges vary by lab)"
    } else if ft_pmol < 225.0 {
        "Low calculated free testosterone — possible hypogonadism"
    } else if ft_pmol <= 725.0 {
        "Normal calculated free testosterone"
    } else {
        "Elevated calculated free testosterone"
    };

    Some(DomainScore {
        domain: DOMAIN.into(),
        system: "Vermeulen cFT".into(),
        score: ft_pmol,
        interpretation: format!("{interp} ({ft_pmol:.1} pmol/L)"),
        components: vec!["Total Testosterone".into(), "SHBG".into(), "Albumin".into()],
        version: "Vermeulen 1999".into(),
    })
}

/// LH:FSH Ratio.
pub fn lh_fsh_ratio(m: &MarkerLookup, profile: &UserProfile) -> Option<DomainScore> {
    let lh = m.val("lh")?;
    let fsh = m.val("fsh")?;
    if fsh <= 0.0 { return None; }
    let score = lh / fsh;

    let is_female = profile.sex.as_deref().map(|s| s.to_lowercase())
        .map(|s| s == "female" || s == "f")
        .unwrap_or(false);

    let interp = if is_female {
        if score >= 2.0 {
            "Elevated LH:FSH ratio — suggestive of PCOS"
        } else if score < 0.5 {
            "Low LH:FSH ratio — possible diminished ovarian reserve"
        } else {
            "Normal LH:FSH ratio"
        }
    } else {
        "LH:FSH ratio (male — limited diagnostic standardisation)"
    };

    Some(DomainScore {
        domain: DOMAIN.into(),
        system: "LH:FSH Ratio".into(),
        score,
        interpretation: format!("{interp} ({score:.2})"),
        components: vec!["LH".into(), "FSH".into()],
        version: "Clinical consensus".into(),
    })
}

/// HOMA-IR as hormonal/insulin axis score (shared formula with metabolic).
pub fn homa_ir_hormonal(m: &MarkerLookup) -> Option<DomainScore> {
    let insulin = m.val("insulin")?;
    let glucose = m.val("glucose")?;
    let glucose_mgdl = glucose * 18.016;
    let score = insulin * glucose_mgdl / 405.0;

    let interp = if score < 1.0 {
        "Optimal insulin axis function"
    } else if score < 2.0 {
        "Normal insulin axis"
    } else if score < 3.0 {
        "Early insulin axis dysfunction"
    } else {
        "Significant insulin resistance"
    };

    Some(DomainScore {
        domain: DOMAIN.into(),
        system: "HOMA-IR (Insulin Axis)".into(),
        score,
        interpretation: interp.into(),
        components: vec!["Insulin (Fasting)".into(), "Glucose (Fasting)".into()],
        version: "Matthews 1985".into(),
    })
}

/// Collect all hormonal domain scores.
pub fn all_scores(m: &MarkerLookup, profile: &UserProfile) -> Vec<DomainScore> {
    let scorers: Vec<Option<DomainScore>> = vec![
        spina_gt(m),
        spina_gd(m),
        jostel_tshi(m),
        fai(m, profile),
        vermeulen_free_t(m, profile),
        lh_fsh_ratio(m, profile),
        homa_ir_hormonal(m),
    ];
    scorers.into_iter().flatten().collect()
}
