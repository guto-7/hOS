export interface DiagnosticTemplate {
  title: string;
  category: string;
  defaultChildren: string[];
}

export const DIAGNOSTIC_TEMPLATES: DiagnosticTemplate[] = [
  {
    title: "Blood Work",
    category: "hematology",
    defaultChildren: ["CBC", "Metabolic Panel", "Lipid Panel"],
  },
  {
    title: "Imaging",
    category: "imaging",
    defaultChildren: ["X-Ray", "MRI", "CT Scan"],
  },
  {
    title: "Cardiology",
    category: "cardiology",
    defaultChildren: ["ECG", "Echocardiogram", "Stress Test"],
  },
  {
    title: "Custom",
    category: "general",
    defaultChildren: [],
  },
];
