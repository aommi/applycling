const pptxgen = require("pptxgenjs");

const pres = new pptxgen();
pres.layout = "LAYOUT_16x9";
pres.author = "Amirali";
pres.title = "applycling — Two Products, One Engine";

// ── Palette ──
const C = {
  bg:     "0A0E27",  // deep navy
  bg2:    "131942",  // lighter navy
  white:  "FFFFFF",
  accent: "4F8CFF",  // electric blue
  muted:  "8E99B0",  // slate
  dim:    "2A2F52",  // dark accent
  green:  "3DDC84",  // for success/positive
};

const FONT_H = "Arial Black";
const FONT_B = "Calibri";

// ── Helper ──
function darkSlide() {
  const s = pres.addSlide();
  s.background = { color: C.bg };
  return s;
}

function footer(s, text) {
  s.addText(text, { x: 0.8, y: 5.05, w: 8.4, h: 0.3, fontSize: 8, color: C.muted, fontFace: FONT_B });
}

// ═══════════════════════════════════════
// SLIDE 1: Title
// ═══════════════════════════════════════
let s = darkSlide();
s.addShape(pres.shapes.RECTANGLE, { x: 0, y: 0, w: 10, h: 0.08, fill: { color: C.accent } });
s.addText("applycling", {
  x: 0.8, y: 1.2, w: 8.4, h: 1.0,
  fontSize: 52, fontFace: FONT_H, color: C.white, bold: true,
});
s.addText("Two Products, One Engine", {
  x: 0.8, y: 2.2, w: 8.4, h: 0.7,
  fontSize: 28, fontFace: FONT_B, color: C.accent,
});
s.addText("An open source agent-native tool + a hosted SaaS workbench.\nSame skills. Same engine. Different users.", {
  x: 0.8, y: 3.2, w: 8.4, h: 0.8,
  fontSize: 14, fontFace: FONT_B, color: C.muted,
});
footer(s, "Amirali · 2026");

// ═══════════════════════════════════════
// SLIDE 2: What applycling does
// ═══════════════════════════════════════
s = darkSlide();
s.addText("What applycling does", {
  x: 0.8, y: 0.5, w: 8.4, h: 0.7,
  fontSize: 32, fontFace: FONT_H, color: C.white,
});
s.addShape(pres.shapes.RECTANGLE, { x: 0.8, y: 1.15, w: 1.2, h: 0.04, fill: { color: C.accent } });

s.addText("Turns a job URL into a complete application package.", {
  x: 0.8, y: 1.6, w: 8.4, h: 0.5,
  fontSize: 18, fontFace: FONT_B, color: C.white, bold: true,
});

const steps = [
  ["①  Paste URL", "User sends a job link"],
  ["②  Scrape + Analyze", "Job description, company context, role intel"],
  ["③  Generate", "Tailored resume, cover letter, positioning brief, email, fit summary"],
  ["④  Package", "Clean PDFs in a dated folder, ready to submit"],
];

steps.forEach(([label, desc], i) => {
  const y = 2.3 + i * 0.65;
  s.addShape(pres.shapes.RECTANGLE, { x: 0.8, y: y, w: 0.06, h: 0.45, fill: { color: C.accent } });
  s.addText(label, { x: 1.1, y: y, w: 3.5, h: 0.35, fontSize: 14, fontFace: FONT_B, color: C.white, bold: true });
  s.addText(desc, { x: 1.1, y: y + 0.28, w: 7.5, h: 0.25, fontSize: 11, fontFace: FONT_B, color: C.muted });
});

footer(s, "What applycling does");

// ═══════════════════════════════════════
// SLIDE 3: The Insight
// ═══════════════════════════════════════
s = darkSlide();
s.addText("Two Different Users", {
  x: 0.8, y: 0.5, w: 8.4, h: 0.7,
  fontSize: 32, fontFace: FONT_H, color: C.white,
});
s.addShape(pres.shapes.RECTANGLE, { x: 0.8, y: 1.15, w: 1.2, h: 0.04, fill: { color: C.accent } });

// Left column
s.addShape(pres.shapes.RECTANGLE, { x: 0.8, y: 1.6, w: 3.8, h: 3.0, fill: { color: C.bg2 } });
s.addText("The Individual", {
  x: 1.1, y: 1.8, w: 3.3, h: 0.4,
  fontSize: 16, fontFace: FONT_H, color: C.accent,
});
const individual = [
  "Applying to a few jobs",
  "Wants great results, not a dashboard",
  "Already has an AI agent",
  "Won't pay for \"yet another tool\"",
  "Will tell friends if it works",
];
individual.forEach((line, i) => {
  s.addText("— " + line, {
    x: 1.1, y: 2.3 + i * 0.4, w: 3.3, h: 0.35,
    fontSize: 11, fontFace: FONT_B, color: C.white,
  });
});

// Right column
s.addShape(pres.shapes.RECTANGLE, { x: 5.4, y: 1.6, w: 3.8, h: 3.0, fill: { color: C.bg2 } });
s.addText("The Power User", {
  x: 5.7, y: 1.8, w: 3.3, h: 0.4,
  fontSize: 16, fontFace: FONT_H, color: C.green,
});
const power = [
  "Running a job search (20+ applications)",
  "Wants to track, review, regenerate",
  "Needs a workbench, analytics, history",
  "Will pay for productivity",
  "Grew out of the free version",
];
power.forEach((line, i) => {
  s.addText("— " + line, {
    x: 5.7, y: 2.3 + i * 0.4, w: 3.3, h: 0.35,
    fontSize: 11, fontFace: FONT_B, color: C.white,
  });
});

footer(s, "Two different users · Two products");

// ═══════════════════════════════════════
// SLIDE 4: Architecture
// ═══════════════════════════════════════
s = darkSlide();
s.addText("Architecture", {
  x: 0.8, y: 0.5, w: 8.4, h: 0.7,
  fontSize: 32, fontFace: FONT_H, color: C.white,
});
s.addShape(pres.shapes.RECTANGLE, { x: 0.8, y: 1.15, w: 1.2, h: 0.04, fill: { color: C.accent } });

const layers = [
  ["Fat Skills (markdown)", "18 files · Orchestrator + content skills\nJudgment, policy, LLM prompts · What + when", C.accent],
  ["Sharp Tools (scripts)", "4 files · Scrape, clean, render, assemble\nDeterministic, repeatable, testable", C.green],
  ["Thin Harness (agent)", "Hermes / Claude Code / OpenClaw\nTool calling, file I/O, error handling\nNothing gets reinvented", C.muted],
];

layers.forEach(([label, desc, color], i) => {
  const y = 1.6 + i * 1.05;
  s.addShape(pres.shapes.RECTANGLE, { x: 0.8, y: y, w: 8.4, h: 0.85, fill: { color: C.bg2 } });
  s.addShape(pres.shapes.RECTANGLE, { x: 0.8, y: y, w: 0.06, h: 0.85, fill: { color: color } });
  s.addText(label, { x: 1.2, y: y + 0.05, w: 7.8, h: 0.3, fontSize: 14, fontFace: FONT_B, color: color, bold: true });
  s.addText(desc, { x: 1.2, y: y + 0.35, w: 7.8, h: 0.45, fontSize: 10, fontFace: FONT_B, color: C.muted });
});

footer(s, "Fat Skills · Sharp Tools · Thin Harness (Garry Tan's gbrain pattern)");

// ═══════════════════════════════════════
// SLIDE 5: applycling (open source)
// ═══════════════════════════════════════
s = darkSlide();
s.addText("applycling  (open source)", {
  x: 0.8, y: 0.5, w: 8.4, h: 0.7,
  fontSize: 32, fontFace: FONT_H, color: C.accent,
});
s.addShape(pres.shapes.RECTANGLE, { x: 0.8, y: 1.15, w: 1.2, h: 0.04, fill: { color: C.accent } });

s.addText([
  { text: "Telegram", options: { color: C.accent } },
  { text: " → \"apply to https://jobs.lever.co/company/role\"" },
], {
  x: 0.8, y: 1.6, w: 8.4, h: 0.5,
  fontSize: 16, fontFace: FONT_B, color: C.white,
});

s.addText([
  { text: "One command to install.", options: { color: C.white, bold: true } },
  { text: " Zero infrastructure. No signup. No monthly fee." },
], {
  x: 0.8, y: 2.0, w: 8.4, h: 0.4,
  fontSize: 12, fontFace: FONT_B, color: C.muted,
});

const ossFeatures = [
  "Full application package (resume, cover letter, positioning brief, email, fit summary)",
  "Works on any agent runtime: Hermes, Claude Code, OpenClaw",
  "Fork it, tweak the cover letter style, contribute back",
  "MIT license. The engine is public. The skills are the moat.",
];
ossFeatures.forEach((line, i) => {
  s.addText("— " + line, {
    x: 0.8, y: 2.6 + i * 0.4, w: 8.4, h: 0.35,
    fontSize: 12, fontFace: FONT_B, color: C.white,
  });
});

s.addShape(pres.shapes.RECTANGLE, { x: 0.8, y: 4.4, w: 8.4, h: 0.5, fill: { color: C.bg2 } });
s.addText("Free · Agent-native · MIT · github.com/amirali/applycling", {
  x: 1.0, y: 4.45, w: 8.0, h: 0.4,
  fontSize: 11, fontFace: FONT_B, color: C.accent, align: "center",
});

footer(s, "applycling — open source");

// ═══════════════════════════════════════
// SLIDE 6: applycling Workbench (SaaS)
// ═══════════════════════════════════════
s = darkSlide();
s.addText("applycling Workbench  (SaaS)", {
  x: 0.8, y: 0.5, w: 8.4, h: 0.7,
  fontSize: 32, fontFace: FONT_H, color: C.green,
});
s.addShape(pres.shapes.RECTANGLE, { x: 0.8, y: 1.15, w: 1.2, h: 0.04, fill: { color: C.green } });

s.addText("Everything in applycling, plus the workbench.", {
  x: 0.8, y: 1.6, w: 8.4, h: 0.5,
  fontSize: 16, fontFace: FONT_B, color: C.white, bold: true,
});

const saasFeatures = [
  "Web dashboard — all your applications in one place",
  "Job status tracking — saved, applied, interviewing, offer, rejected",
  "Review and regenerate individual packages with one click",
  "Analytics — which resumes are getting responses?",
  "Multi-job management — running a job search, not applying to one role",
];
saasFeatures.forEach((line, i) => {
  s.addText("— " + line, {
    x: 0.8, y: 2.2 + i * 0.4, w: 8.4, h: 0.35,
    fontSize: 12, fontFace: FONT_B, color: C.white,
  });
});

s.addShape(pres.shapes.RECTANGLE, { x: 0.8, y: 4.4, w: 8.4, h: 0.5, fill: { color: C.bg2 } });
s.addText("Subscription · Hosted · applycling.com", {
  x: 1.0, y: 4.45, w: 8.0, h: 0.4,
  fontSize: 11, fontFace: FONT_B, color: C.green, align: "center",
});

footer(s, "applycling Workbench — SaaS");

// ═══════════════════════════════════════
// SLIDE 7: The Funnel
// ═══════════════════════════════════════
s = darkSlide();
s.addText("Why This Works", {
  x: 0.8, y: 0.5, w: 8.4, h: 0.7,
  fontSize: 32, fontFace: FONT_H, color: C.white,
});
s.addShape(pres.shapes.RECTANGLE, { x: 0.8, y: 1.15, w: 1.2, h: 0.04, fill: { color: C.accent } });

const why = [
  ["Open source is the funnel", "Users try applycling for free. They apply to 8 jobs. They think: \"I want to see all of these in one place.\" They become Workbench customers — not because they were sold to, but because they outgrew the free version."],
  ["Skills are the moat", "18 markdown files encode years of application-writing judgment. The open source version keeps them sharp through forks, tweaks, and contributions. Every improvement benefits both products."],
  ["One engine, no fork", "Both products run the same skills and tools. Workbench adds UI, tracking, and analytics — not a different pipeline."],
  ["Agent-native distribution", "No app store. No npm install. No deployment. Users who already run an agent get applycling by dropping a folder."],
];

why.forEach(([label, desc], i) => {
  const y = 1.5 + i * 0.85;
  s.addText(label, { x: 0.8, y: y, w: 8.4, h: 0.3, fontSize: 14, fontFace: FONT_B, color: C.accent, bold: true });
  s.addText(desc, { x: 0.8, y: y + 0.28, w: 8.4, h: 0.5, fontSize: 11, fontFace: FONT_B, color: C.muted });
});

footer(s, "Why this works");

// ═══════════════════════════════════════
// SLIDE 8: The Eval Gate
// ═══════════════════════════════════════
s = darkSlide();
s.addText("The Eval Gate", {
  x: 0.8, y: 0.5, w: 8.4, h: 0.7,
  fontSize: 32, fontFace: FONT_H, color: C.white,
});
s.addShape(pres.shapes.RECTANGLE, { x: 0.8, y: 1.15, w: 1.2, h: 0.04, fill: { color: C.accent } });

s.addText("Before shipping: 20 real URLs through the agent. Prove it works.", {
  x: 0.8, y: 1.5, w: 8.4, h: 0.5,
  fontSize: 14, fontFace: FONT_B, color: C.white, bold: true,
});

const criteria = [
  ["Package completeness", "All files present in 18/20 runs"],
  ["PDF success", "PDFs render in 19/20 runs"],
  ["Never-fabricate", "0 hallucinated experiences in 20/20 spot checks"],
  ["Retry behavior", "Failed steps retry once, skip with warning"],
  ["File naming", "Consistent format in 20/20 runs"],
  ["User intervention", "≤1 manual fix per run on average"],
];

criteria.forEach(([label, desc], i) => {
  const y = 2.2 + i * 0.42;
  s.addText(label, { x: 0.8, y: y, w: 3.5, h: 0.35, fontSize: 11, fontFace: FONT_B, color: C.white, bold: true });
  s.addText(desc, { x: 4.5, y: y, w: 4.7, h: 0.35, fontSize: 11, fontFace: FONT_B, color: C.muted });
});

s.addShape(pres.shapes.RECTANGLE, { x: 0.8, y: 4.5, w: 8.4, h: 0.45, fill: { color: C.bg2 } });
s.addText("Pass → ship agent-native. Fail → fall back to thin Python orchestrator. Either way, skills stay public.", {
  x: 1.0, y: 4.55, w: 8.0, h: 0.35,
  fontSize: 11, fontFace: FONT_B, color: C.accent, align: "center",
});

footer(s, "Eval gate");

// ═══════════════════════════════════════
// SLIDE 9: One Engine
// ═══════════════════════════════════════
s = darkSlide();
s.addText("One Engine, No Fork", {
  x: 0.8, y: 0.5, w: 8.4, h: 0.7,
  fontSize: 32, fontFace: FONT_H, color: C.white,
});
s.addShape(pres.shapes.RECTANGLE, { x: 0.8, y: 1.15, w: 1.2, h: 0.04, fill: { color: C.accent } });

// Three columns
const cols = [
  { label: "applycling", sub: "Public repo", color: C.accent, items: ["18 skill files", "4 deterministic tools", "Orchestrator skill", "setup.sh", "eval gate", "MIT license"] },
  { label: "Shared Engine", sub: "Both call these", color: C.white, items: ["skills/*/SKILL.md", "tools/{scrape, clean,", "  render, assemble}", "Same sequence", "Same output"] },
  { label: "Workbench", sub: "Private repo", color: C.green, items: ["Web UI (FastAPI)", "Job tracker (Postgres)", "Multi-job management", "Analytics", "Auth + subscriptions"] },
];

cols.forEach((col, i) => {
  const x = 0.6 + i * 3.15;
  s.addShape(pres.shapes.RECTANGLE, { x: x, y: 1.5, w: 2.9, h: 3.2, fill: { color: C.bg2 } });
  s.addText(col.label, { x: x + 0.15, y: 1.65, w: 2.6, h: 0.35, fontSize: 15, fontFace: FONT_H, color: col.color });
  s.addText(col.sub, { x: x + 0.15, y: 1.95, w: 2.6, h: 0.25, fontSize: 9, fontFace: FONT_B, color: C.muted });
  col.items.forEach((item, j) => {
    s.addText("— " + item, { x: x + 0.15, y: 2.4 + j * 0.32, w: 2.6, h: 0.28, fontSize: 10, fontFace: FONT_B, color: C.white });
  });
});

footer(s, "One engine · Two repos · Zero drift");

// ═══════════════════════════════════════
// SLIDE 10: Next Steps
// ═══════════════════════════════════════
s = darkSlide();
s.addText("Next Steps", {
  x: 0.8, y: 0.5, w: 8.4, h: 0.7,
  fontSize: 32, fontFace: FONT_H, color: C.white,
});
s.addShape(pres.shapes.RECTANGLE, { x: 0.8, y: 1.15, w: 1.2, h: 0.04, fill: { color: C.accent } });

const next = [
  ["Phase 1", "Write the orchestrator skill + 4 deterministic tools", "Week 1"],
  ["Phase 2", "Run the eval gate — 20 real URLs through Hermes", "Week 1-2"],
  ["Phase 3", "Ship applycling to public GitHub", "Week 2"],
  ["Phase 4", "Wire Workbench to consume same skills + tools", "Week 2-3"],
];

next.forEach(([label, desc, time], i) => {
  const y = 1.6 + i * 0.8;
  s.addShape(pres.shapes.RECTANGLE, { x: 0.8, y: y, w: 0.5, h: 0.55, fill: { color: C.accent } });
  s.addText(label, { x: 0.9, y: y + 0.02, w: 0.4, h: 0.3, fontSize: 9, fontFace: FONT_B, color: C.white, align: "center" });
  s.addText(desc, { x: 1.6, y: y + 0.05, w: 5.5, h: 0.3, fontSize: 14, fontFace: FONT_B, color: C.white, bold: true });
  s.addText(time, { x: 7.5, y: y + 0.05, w: 1.7, h: 0.3, fontSize: 11, fontFace: FONT_B, color: C.muted, align: "right" });
});

s.addShape(pres.shapes.RECTANGLE, { x: 0.8, y: 4.7, w: 8.4, h: 0.45, fill: { color: C.bg2 } });
s.addText("Open source ships first. SaaS follows. Skills improve both.", {
  x: 1.0, y: 4.75, w: 8.0, h: 0.35,
  fontSize: 12, fontFace: FONT_B, color: C.accent, align: "center",
});

footer(s, "Next steps");

// ═══════════════════════════════════════
// WRITE
// ═══════════════════════════════════════
const outPath = "/Users/amirali/Documents/dev/applycling/docs/planning/applycling-two-products.pptx";
pres.writeFile({ fileName: outPath }).then(() => {
  console.log("Written: " + outPath);
});
