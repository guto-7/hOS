**Track 1: Clinical / Patient-Facing Applications**

If your app will be used to inform real patient care, you need FDA-cleared tools. These are enterprise products, not simple APIs — they integrate with hospital systems (PACS, EHR) and are sold to health systems, not individual developers. The main players are:

- **Aidoc** — a vendor-neutral platform that runs 24/7 to automatically analyze CT scans, MRIs, and X-rays for acute and incidental findings across neuroimaging, chest, abdominal, and vascular specialties [Intuitionlabs](https://intuitionlabs.ai/software/radiology-workflow-informatics/radiologist-productivity-tools/aidoc). It holds the most FDA clearances (17+) of any clinical AI company, but is sold as an enterprise solution to hospitals.
- **Viz.ai** — FDA-cleared algorithms that rapidly identify large-vessel occlusions or intracranial bleeds on CT/MRI [IntuitionLabs](https://intuitionlabs.ai/articles/imaging-pathology-ai-vendors), deployed in 1,800+ hospitals.
- **Annalise.ai** — covers 20+ findings across X-ray, CT, and MRI in one platform [Healthcare Readers](https://healthcarereaders.com/medical-devices/medical-ai-imaging-diagnostics-companies).
- **Subtle Medical** — FDA-cleared SubtleMR™ tool allows MRI scans to be done faster or at lower dose while preserving image quality [IntuitionLabs](https://intuitionlabs.ai/articles/imaging-pathology-ai-vendors).
- **Arterys** — offers AI tools for cardiac MRI (e.g. heart chamber quantification) [IntuitionLabs](https://intuitionlabs.ai/articles/imaging-pathology-ai-vendors), cleared by the FDA as early as 2016.

These are not plug-and-play APIs for developers — they require enterprise contracts, compliance infrastructure, and hospital partnerships.

---

**Track 2: Research / Non-Clinical Applications**

If you're building a research tool, a pipeline for a lab, or anything **not** making clinical decisions for individual patients, you can freely use open-source models:

- **SynthSeg / SynthSeg+** — publicly available with FreeSurfer; can robustly analyze scans of any contrast and resolution without retraining [PNAS](https://www.pnas.org/doi/10.1073/pnas.2216399120). Excellent for brain MRI segmentation and volumetry.
- **FastSurfer** — fully open-source under an Apache license; extracts quantitative measurements from brain MRI, validated across different scanners, field strengths, ages, and diseases [Deep-mi](https://deep-mi.org/FastSurfer/dev/overview/intro.html). Note: explicitly states it should not be used for clinical decision support in individual cases.
- **TotalSegmentator MRI** — a sequence-agnostic open-source segmentation model covering 80 anatomical structures, which recently won RSNA's top scientific award [Radiological Society of North America](https://www.rsna.org/media/press/2025/2627).
- **nnU-Net** — the gold-standard self-configuring segmentation framework, open source, used widely in research.
- **MONAI** — an open-source AI framework that bridges research and clinical deployment in medical imaging [MONAI](https://monai.io/), with a model zoo of pretrained MRI models.