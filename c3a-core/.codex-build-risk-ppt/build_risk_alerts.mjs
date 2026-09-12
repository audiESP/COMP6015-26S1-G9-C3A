import fs from 'node:fs/promises';
import path from 'node:path';
import { pathToFileURL } from 'node:url';
import { Presentation, PresentationFile } from '@oai/artifact-tool';

const workspaceDir = '/Users/xu/Documents/code/c3a_/COMP6015-26S1-G9-C3A/c3a-core';
const skillDir = '/Users/xu/.codex/plugins/cache/openai-primary-runtime/presentations/26.909.12148/skills/presentations';
const buildDir = path.join(workspaceDir, '.codex-build-risk-ppt');
const stagingDir = path.join(buildDir, 'staging');
const outputDir = path.join(workspaceDir, 'output');
const finalPath = path.join(outputDir, 'risk-alerts-implementation-en.pptx');
const runtimePython = '/Users/xu/.cache/codex-runtimes/codex-primary-runtime/dependencies/python/bin/python3';
const { finalizePresentation } = await import(pathToFileURL(path.join(skillDir, 'container_tools/artifact_tool_utils.mjs')).href);

await fs.mkdir(stagingDir, { recursive: true });
await fs.mkdir(outputDir, { recursive: true });
await fs.symlink('/Users/xu/.cache/codex-runtimes/codex-primary-runtime/dependencies/node/node_modules', path.join(buildDir, 'node_modules')).catch(() => {});
await fs.rm(finalPath, { force: true });

const W = 1280, H = 720;
const font = 'PingFang SC';
const C = {
  navy: '#102A43', ink: '#243B53', muted: '#627D98', paper: '#F7FAFC',
  teal: '#008C95', tealLight: '#DDF4F2', green: '#2F855A', amber: '#D97706',
  red: '#C2413B', blue: '#2563EB', line: '#D9E2EC', white: '#FFFFFF', slate: '#486581'
};

const pres = Presentation.create({ slideSize: { width: W, height: H } });

function shape(slide, geometry, x, y, w, h, fill = 'none', line = 'none') {
  const normalizedFill = fill === 'none'
    ? 'none'
    : typeof fill === 'string'
      ? { type: 'solid', color: fill }
      : { type: 'solid', color: fill.color };
  return slide.shapes.add({ geometry, position: { left: x, top: y, width: w, height: h }, fill: normalizedFill, line: line === 'none' ? { fill: 'none', width: 0 } : line });
}
function text(slide, value, x, y, w, h, opts = {}) {
  const s = shape(slide, 'textbox', x, y, w, h);
  s.text = value;
  s.text.style = { typeface: font, fontSize: opts.size ?? 20, color: opts.color ?? C.ink, bold: opts.bold ?? false, autoFit: 'shrink', ...opts.style };
  return s;
}
function rect(slide, x, y, w, h, color, radius = true) {
  return shape(slide, radius ? 'roundRect' : 'rect', x, y, w, h, { color }, { fill: color, width: 0 });
}
function line(slide, x, y, w, h, color = C.line, width = 2) {
  return shape(slide, 'line', x, y, w, h, 'none', { fill: color, width });
}
function header(slide, n, title, subtitle = '') {
  text(slide, `0${n}`, 64, 40, 45, 24, { size: 14, color: C.teal, bold: true });
  text(slide, title, 64, 72, 1040, 54, { size: 35, color: C.navy, bold: true });
  if (subtitle) text(slide, subtitle, 64, 132, 1030, 30, { size: 17, color: C.muted });
  line(slide, 64, 172, 1152, 0, C.line, 1);
  text(slide, 'C3A Care Risk Alerts', 64, 680, 270, 18, { size: 11, color: C.muted });
  text(slide, String(n), 1195, 680, 20, 18, { size: 11, color: C.muted, style: { alignment: 'right' } });
}
function pill(slide, value, x, y, w, color, fg = C.white) {
  rect(slide, x, y, w, 30, color);
  text(slide, value, x + 10, y + 6, w - 20, 18, { size: 12, color: fg, bold: true, style: { alignment: 'center' } });
}
function node(slide, title, body, x, y, w, h, accent) {
  rect(slide, x, y, w, h, C.white);
  rect(slide, x, y, 7, h, accent, false);
  text(slide, title, x + 24, y + 20, w - 42, 28, { size: 20, color: C.navy, bold: true });
  text(slide, body, x + 24, y + 57, w - 42, h - 72, { size: 15, color: C.slate, style: { breakLine: false } });
}
function connector(slide, x, y, w) {
  line(slide, x, y, w, 0, C.teal, 2);
  shape(slide, 'rightArrow', x + w - 12, y - 7, 14, 14, { color: C.teal }, { fill: C.teal, width: 0 });
}
function notes(slide, value) { slide.speakerNotes.textFrame.setText(value); }

// 1 Cover
{
  const s = pres.slides.add(); s.background.fill = C.navy;
  rect(s, 0, 0, W, H, C.navy, false);
  rect(s, 806, 0, 474, 720, '#0F3C50', false);
  shape(s, 'ellipse', 891, 115, 265, 265, { color: '#155E67' }, { fill: '#155E67', width: 0 });
  shape(s, 'ellipse', 956, 180, 265, 265, { color: '#0C5361' }, { fill: '#0C5361', width: 0 });
  shape(s, 'ellipse', 850, 342, 214, 214, { color: '#16717B' }, { fill: '#16717B', width: 0 });
  text(s, 'C3A Care\nRisk Alerts', 78, 172, 640, 150, { size: 54, color: C.white, bold: true });
  text(s, 'Implementation overview', 82, 345, 450, 32, { size: 24, color: '#B9E9E5' });
  line(s, 82, 412, 140, 0, '#47D7CE', 4);
  text(s, 'Medication, location and care-task monitoring\nwith actionable alerts and AI-aware guidance', 82, 448, 570, 64, { size: 20, color: '#D9EAF2' });
  text(s, 'COMP6015 · C3A Core', 82, 639, 240, 22, { size: 14, color: '#A9C7D5' });
  notes(s, 'Overview of the risk alert feature implemented for the C3A care workflow.');
}

// 2 Overview
{
  const s = pres.slides.add(); s.background.fill = C.paper; header(s, 2, 'Risk alert capability', 'The system detects exceptions during a visit and keeps the response connected to the care workflow.');
  node(s, 'Medication risk', 'Medication not taken, delayed support, declined medication, unavailable medication or an unconfirmed outcome.', 64, 228, 345, 235, C.red);
  node(s, 'GPS location risk', 'The server compares check-in and check-out coordinates with the planned visit location and allowed distance.', 467, 228, 345, 235, C.blue);
  node(s, 'Care task risk', 'Tasks marked delayed, skipped or incomplete, plus pending tasks that pass their due time.', 870, 228, 345, 235, C.amber);
  text(s, 'Each rule creates or updates a visit-level alert with a stable key, preventing duplicate alerts for the same issue.', 137, 541, 1006, 38, { size: 20, color: C.navy, bold: true, style: { alignment: 'center' } });
  notes(s, 'The implementation currently covers medication, GPS location and care task risks.');
}

// 3 Detection
{
  const s = pres.slides.add(); s.background.fill = C.white; header(s, 3, 'Server-side risk detection', 'Rules use persisted care data rather than relying only on client-side status labels.');
  text(s, 'Inputs', 82, 220, 150, 28, { size: 20, color: C.teal, bold: true });
  text(s, 'Rule evaluation', 510, 220, 190, 28, { size: 20, color: C.teal, bold: true });
  text(s, 'Result', 950, 220, 150, 28, { size: 20, color: C.teal, bold: true });
  node(s, 'Medication support', 'Status, medication item outcome and notes', 64, 270, 275, 105, C.red);
  node(s, 'Task status', 'Pending, delayed, issue, skipped and due time', 64, 405, 275, 105, C.amber);
  node(s, 'Location snapshot', 'GPS coordinates, planned point and threshold', 64, 540, 275, 105, C.blue);
  node(s, 'Rule modules', 'Medication rule map\nChecklist monitor\nLocation monitor with Haversine distance', 466, 330, 340, 210, C.teal);
  node(s, 'Risk alert', 'Severity, type, message, trigger source, visit ID and structured details', 914, 330, 300, 210, C.green);
  connector(s, 350, 458, 98); connector(s, 814, 438, 82);
  notes(s, 'The backend evaluates medication, care-task and location conditions. Location distance is recalculated on the server using the Haversine formula.');
}

// 4 lifecycle
{
  const s = pres.slides.add(); s.background.fill = C.paper; header(s, 4, 'Alert lifecycle and audit trail', 'Alerts remain visible until staff record an outcome. Each state change is stored for review.');
  const xs = [84, 342, 600, 858];
  const states = [
    ['Active', 'The rule detects an unresolved issue', C.red],
    ['Acknowledged', 'A worker confirms the alert and starts review', C.amber],
    ['Resolved', 'The issue has been handled', C.green],
    ['Dismissed', 'A worker records that follow-up is not required', C.slate],
  ];
  states.forEach(([name, body, color], i) => {
    shape(s, 'ellipse', xs[i] + 58, 260, 120, 120, { color }, { fill: color, width: 0 });
    text(s, name, xs[i] + 64, 302, 108, 28, { size: 17, color: C.white, bold: true, style: { alignment: 'center' } });
    text(s, body, xs[i], 410, 236, 66, { size: 15, color: C.slate, style: { alignment: 'center' } });
    if (i < 3) connector(s, xs[i] + 195, 320, 54);
  });
  rect(s, 164, 548, 950, 68, '#EAF3F4');
  text(s, 'Audit record: previous state · resulting state · worker · role · timestamp · optional review note', 190, 570, 900, 26, { size: 18, color: C.navy, bold: true, style: { alignment: 'center' } });
  notes(s, 'Risk alerts support active, acknowledged, resolved and dismissed states. The database records who performed each action, when it happened and any note.');
}

// 5 UI & access
{
  const s = pres.slides.add(); s.background.fill = C.white; header(s, 5, 'Care workflow integration', 'The risk state appears in the patient view and stays synchronized with the active visit.');
  text(s, 'Patient page', 100, 220, 250, 32, { size: 24, color: C.navy, bold: true });
  text(s, 'Things to watch shows open alerts.\nAlert history keeps resolved and dismissed items visible.', 100, 273, 342, 66, { size: 17, color: C.slate });
  line(s, 100, 368, 326, 0, C.line, 1);
  pill(s, 'Review', 100, 400, 90, C.amber); pill(s, 'Resolve', 208, 400, 94, C.green); pill(s, 'Dismiss', 320, 400, 98, C.slate);
  text(s, 'Workers can add an optional review note with every action.', 100, 457, 330, 52, { size: 16, color: C.muted });
  shape(s, 'rightArrow', 512, 346, 105, 64, { color: C.teal }, { fill: C.teal, width: 0 });
  node(s, 'Scenario refresh', 'After an action, the UI reloads the current scenario so tasks, visit status, alerts and recent events remain consistent.', 668, 267, 440, 160, C.teal);
  rect(s, 668, 470, 440, 108, '#F0F7FF');
  text(s, 'Access checks', 694, 491, 160, 26, { size: 19, color: C.blue, bold: true });
  text(s, 'Visit reads and updates include worker ID and role. The API returns 403 when the worker cannot access the visit.', 694, 526, 388, 35, { size: 15, color: C.slate });
  notes(s, 'The Patient page provides review, resolve and dismiss actions. Visit APIs also enforce worker and role context.');
}

// 6 AI
{
  const s = pres.slides.add(); s.background.fill = C.paper; header(s, 6, 'Risk-aware AI assistance', 'The chat request sends current risk context to the model so answers reflect the active care situation.');
  node(s, 'Current context', 'Patient profile\nVisit details\nCare tasks\nMedication support record\nOpen risk alerts', 66, 248, 270, 250, C.teal);
  connector(s, 354, 370, 118);
  node(s, 'Prompt preparation', 'The prompt places supplied context ahead of general guidance. It includes medication state, task state, alert type, severity, details and review note.', 492, 248, 300, 250, C.blue);
  connector(s, 810, 370, 118);
  node(s, 'Answer with sources', 'The response can identify guideline evidence, patient records, visit context or general model guidance.', 948, 248, 270, 250, C.green);
  text(s, 'Example: if medication support is delayed, the model receives that fact and can give care-plan-focused follow-up guidance.', 122, 562, 1038, 38, { size: 19, color: C.navy, bold: true, style: { alignment: 'center' } });
  notes(s, 'The AI receives the current open risks, including medication and care-task states. The UI renders structured source references below the answer.');
}

// 7 safety
{
  const s = pres.slides.add(); s.background.fill = C.white; header(s, 7, 'AI safety and traceability', 'The assistant uses the supplied care context as its main factual basis and exposes the evidence used.');
  rect(s, 64, 224, 535, 323, '#F0F8F7');
  text(s, 'Prompt guardrails', 96, 260, 300, 30, { size: 25, color: C.navy, bold: true });
  text(s, '• Do not invent patient information\n• Do not make a diagnosis\n• Do not recommend an additional dose\n• When evidence is insufficient, advise the user to follow the care plan or contact a nurse or supervisor', 96, 320, 445, 170, { size: 18, color: C.ink });
  rect(s, 666, 224, 550, 323, '#F5F8FC');
  text(s, 'Sources used', 700, 260, 240, 30, { size: 25, color: C.navy, bold: true });
  text(s, 'Each response identifies the information used to produce it:', 700, 316, 450, 25, { size: 17, color: C.slate });
  pill(s, 'Guideline', 700, 365, 104, C.teal); pill(s, 'Patient record', 822, 365, 130, '#7652A8'); pill(s, 'Visit context', 970, 365, 122, C.amber);
  pill(s, 'General guidance', 700, 414, 150, C.slate);
  text(s, 'References can include a source label, reason, document details, page range and record type.', 700, 473, 440, 38, { size: 16, color: C.slate });
  notes(s, 'The safety prompt prevents invented facts, diagnoses and additional-dose advice. Structured sources make the answer traceable.');
}

// 8 summary
{
  const s = pres.slides.add(); s.background.fill = C.navy;
  text(s, 'Risk alert workflow', 74, 66, 550, 52, { size: 38, color: C.white, bold: true });
  text(s, 'A connected workflow from exception detection to accountable follow-up and safer AI support.', 76, 128, 800, 30, { size: 19, color: '#B9E9E5' });
  const steps = [
    ['1', 'Care data', 'Medication, tasks and location'],
    ['2', 'Rules', 'Server-side risk evaluation'],
    ['3', 'Alert', 'Persistent visit-level risk state'],
    ['4', 'Action', 'Staff review with audit history'],
    ['5', 'AI context', 'Risk-aware answer with sources'],
  ];
  steps.forEach(([num, title, body], i) => {
    const x = 76 + i * 228;
    shape(s, 'ellipse', x, 282, 58, 58, { color: '#47D7CE' }, { fill: '#47D7CE', width: 0 });
    text(s, num, x, 297, 58, 23, { size: 19, color: C.navy, bold: true, style: { alignment: 'center' } });
    text(s, title, x, 366, 190, 27, { size: 19, color: C.white, bold: true });
    text(s, body, x, 405, 180, 50, { size: 15, color: '#B6D3DC' });
    if (i < 4) connector(s, x + 68, 311, 130);
  });
  line(s, 76, 542, 1128, 0, '#2C5B6A', 1);
  text(s, 'Outcome: the platform can identify risks early, preserve the handling record and give the AI the context it needs for safer assistance.', 76, 578, 1080, 52, { size: 22, color: C.white, bold: true });
  notes(s, 'Summary of the end-to-end risk alert implementation.');
}

const candidatePath = path.join(stagingDir, 'candidate.pptx');
await (await PresentationFile.exportPptx(pres)).save(candidatePath);
const requirements = { explicitTotalSlideCount: 8, requiredNativeTableOwnerSlides: [], requiredNativeChartOwnerSlides: [] };
await finalizePresentation({
  ...requirements,
  workspaceDir,
  candidatePath,
  finalPath,
  pythonExecutable: runtimePython,
  integrityValidatorPath: path.join(skillDir, 'container_tools/inspect_presentation_package_integrity.py'),
  layoutValidatorPath: path.join(skillDir, 'container_tools/inspect_presentation_layout_geometry.py'),
  layoutArgs: ['--expected-slide-size-emu', '12192000,6858000', '--validate-bullet-geometry', '--validate-heading-fit'],
  fontPolicy: { basis: 'design', families: [font] },
  verifyArtifactToolImport: true,
  receiptPath: path.join(stagingDir, 'risk-alerts-implementation-en.v2.validation.json'),
});
console.log(finalPath);
