import type { APIRequestContext, Page } from '@playwright/test';

// Shared setup for the usability-task E2E suite. See playwright.config.ts
// for prerequisites (backend running, demo data reset).

export const DEMO_PATIENT_NAME = 'Tresa Beier';
export const API_BASE_URL = 'http://127.0.0.1:8000';
export const SEEDED_VISIT_ID = '93e8e38b-439c-4ee8-b724-eb05cf16d327';
export const SEEDED_WORKER_ID = 'cw-001';

/**
 * Completes medication support directly via the gateway API instead of
 * through the UI. "Record medication support" isn't one of the 7 usability
 * tasks itself (Task 7 only needs it out of the way to unlock "Care
 * outcomes and report") — its own per-medicine Taken/Not Taken UI is
 * structurally different from every other task (see MedicationEditor) and
 * deserves its own dedicated test coverage rather than being a fragile
 * incidental step inside Task 7.
 */
export async function completeMedicationSupportViaApi(request: APIRequestContext) {
  await request.patch(`${API_BASE_URL}/visits/${SEEDED_VISIT_ID}/medication-support`, {
    data: {
      status: 'Completed',
      hcwId: SEEDED_WORKER_ID,
      medicationNames: ['Metformin 500 mg', 'Amlodipine 5 mg', 'Atorvastatin 20 mg', 'Vitamin D3 1000 IU'],
      medicationItems: [
        { name: 'Metformin 500 mg', takenStatus: 'Taken' },
        { name: 'Amlodipine 5 mg', takenStatus: 'Taken' },
        { name: 'Atorvastatin 20 mg', takenStatus: 'Taken' },
        { name: 'Vitamin D3 1000 IU', takenStatus: 'Taken' },
      ],
    },
  });
}

/**
 * AI-backed endpoints (patient summary, chat, translate, task materials,
 * visit report) call a local Ollama model and can take anywhere from a few
 * seconds to 1-2 minutes depending on machine load (see
 * FUNCTIONAL_TEST_RESULTS.md "known environment limitations"). This suite
 * mocks them with fast canned responses so it tests UI flow/navigation
 * reliably and quickly — it is not meant to verify AI response quality.
 * Real-AI behaviour is covered by:
 *   - the human-moderated session (USABILITY_TEST_MODERATOR_GUIDE.md)
 *   - the live functional probes in FUNCTIONAL_TEST_RESULTS.md
 * Call this before page.goto() in each test; pass `{ real: true }` for a
 * specific endpoint to let a single test hit the live AI instead (useful
 * for an occasional "does this still really work" run).
 */
export async function mockAiEndpoints(page: Page, opts: { realPatientSummary?: boolean; realChat?: boolean; realTranslate?: boolean; realTaskMaterials?: boolean; realReport?: boolean } = {}) {
  if (!opts.realPatientSummary) {
    await page.route('**/patients/*/summary', route => route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify({
        summary: '1. Overview\nSynthetic test summary.\n2. Active Conditions\nNone recorded.\n3. Medications\nMetformin 500mg.\n4. Allergies\nNo known allergies.\n5. Recent Encounters and Observations\nNone recorded.\n6. CALD and Communication Needs\nVietnamese speaking, interpreter preferred.\n7. Care Focus for this Visit\nRoutine support.',
        patientId: 'stub',
        records: [{ category: 'medication', table: 'c3a_synthea_medications', label: 'Metformin 500mg' }],
      }),
    }));
  }
  if (!opts.realChat) {
    const sourceReferences = [{
      id: 'guideline-1',
      kind: 'guideline',
      label: 'Falls Prevention Guide - p. 4',
      reason: 'Retrieved as relevant guidance for this task.',
      documentTitle: 'Falls Prevention Guide',
      pageStart: 4,
      pageEnd: 4,
    }];
    // The Assistant tab's quick-reply buttons send via the streaming
    // endpoint (useChat.ts), not the plain POST — both are mocked so the
    // test doesn't care which one the UI actually uses.
    await page.route('**/chat/stream', route => route.fulfill({
      status: 200,
      contentType: 'application/x-ndjson',
      body: [
        JSON.stringify({ type: 'token', content: 'Based on the current task, check the patient is seated comfortably and watch for dizziness. [Source 1]' }),
        JSON.stringify({ type: 'done', sources: ['Falls Prevention Guide - p. 4'], sourceReferences, appendSources: true }),
      ].join('\n') + '\n',
    }));
    await page.route('**/chat', route => route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify({
        reply: 'Based on the current task, check the patient is seated comfortably and watch for dizziness. [Source 1]',
        sources: ['Falls Prevention Guide - p. 4'],
        sourceReferences,
      }),
    }));
  }
  if (!opts.realTranslate) {
    await page.route('**/translate', route => route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify({ sourceLanguage: 'English', targetLanguage: 'Vietnamese', translatedText: '[stubbed translation] Vui lòng uống thuốc sau bữa trưa.' }),
    }));
  }
  if (!opts.realTaskMaterials) {
    await page.route('**/training/task-materials', route => route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify({
        query: 'stub',
        items: [{ sourceType: 'internal', title: 'Stubbed guideline excerpt', snippet: 'Stubbed material for E2E test.' }],
        usedWebSearch: false,
        internalCount: 1,
        webCount: 0,
      }),
    }));
  }
  if (!opts.realReport) {
    await page.route('**/visits/*/report', route => route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify({ report: '1. Visit Summary\nStubbed report for E2E test.\n8. Overall Outcome\nVisit completed without incident.' }),
    }));
  }
}

/** Load the 2026-09-04 schedule from app launch, without selecting a visit. */
export async function openSeededSchedule(page: Page) {
  await page.goto('/');
  await page.getByRole('button', { name: /choose.*date/i }).first().click();
  await page.getByRole('button', { name: /previous month/i }).click();
  await page.getByRole('button', { name: 'Friday 4 September 2026', exact: true }).click();
  await page.getByRole('button', { name: /load schedule/i }).click();
  await page.waitForTimeout(500);
}

/** Navigate from app launch to the visit screen for the seeded 2026-09-04 12:00 visit (Tresa Beier). */
export async function openSeededVisit(page: Page) {
  await openSeededSchedule(page);
  // Exact match on the "Up next" card's own CTA only — a looser pattern here
  // previously risked matching an unrelated button elsewhere on the page.
  await page.getByRole('button', { name: /^(Prepare for visit|Continue care|View record)$/ }).click();
  await page.waitForTimeout(1000);
}

/**
 * Navigate from app launch directly to a different visit's screen, via
 * "Your schedule"'s list of the day's other visits. Unlike openSeededVisit
 * (which taps the "Up next" card's own CTA), tapping a schedule row goes
 * straight to that visit's screen — there's no second "Prepare for visit"
 * click to make afterward.
 */
export async function openVisitByPatientName(page: Page, patientName: string) {
  await openSeededSchedule(page);
  const row = page.getByRole('button', { name: new RegExp(patientName) });
  await row.scrollIntoViewIfNeeded();
  await row.click();
  await page.waitForTimeout(1000);
}

/**
 * Start the visit via the manual-location override (not real GPS — see
 * scenarioStore.ts `locationSnapshot`: a non-empty manual reason skips the
 * browser geolocation API entirely, which is unreliable in a headless
 * browser). No-ops if the visit is already started.
 */
export async function startVisitIfNeeded(page: Page) {
  const startButton = page.getByRole('button', { name: 'Start visit', exact: true });
  // isVisible() doesn't wait — right after navigation the button may not
  // have rendered yet, which would make this look "already started" when
  // it's really just not loaded. Give it a real chance to appear first.
  const startVisible = await startButton
    .waitFor({ state: 'visible', timeout: 5000 })
    .then(() => true)
    .catch(() => false);
  if (!startVisible) return; // already started
  await startButton.click({ force: true });
  const checkbox = page.getByRole('checkbox').first();
  await checkbox.scrollIntoViewIfNeeded();
  await checkbox.click({ force: true });
  await page.waitForFunction(
    (el) => el?.getAttribute('aria-checked') === 'true',
    await checkbox.elementHandle(),
    { timeout: 5000 },
  ).catch(() => {});
  await page.getByRole('textbox', { name: /manual location reason/i }).fill('E2E test — headless browser has no GPS.');
  const submit = page.getByRole('button', { name: 'Start visit and check in' });
  await submit.scrollIntoViewIfNeeded();

  // Confirmed live: the backend's POST /visits/{id}/start reliably succeeds
  // within a few seconds, but polling document.body.innerText for "in
  // progress" was unreliable under a slow/throttled renderer (observed:
  // the real request completed in ~7s while the text-polling loop still
  // hadn't seen it 60s+ later). Tie success to the actual network response
  // instead of DOM text, which is the real signal and isn't subject to
  // repaint timing.
  const [response] = await Promise.all([
    page.waitForResponse(
      (res) => /\/visits\/[^/]+\/start$/.test(new URL(res.url()).pathname) && res.request().method() === 'POST',
      { timeout: 60000 },
    ),
    submit.click({ force: true }),
  ]);
  if (!response.ok()) {
    throw new Error(`startVisitIfNeeded: POST /visits/{id}/start returned ${response.status()}`);
  }
  // Give the UI a moment to re-render from the now-started visit. The
  // status label is uppercased by CSS ("IN PROGRESS"), so match without
  // case; options go in the third argument (the second is the page arg).
  await page.waitForFunction(
    () => /in progress/i.test(document.body.innerText),
    undefined,
    { timeout: 15000 },
  ).catch(() => {});
}

function escapeRegExp(s: string) {
  return s.replace(/[.*+?^${}()|[\]\\]/g, '\\$&');
}

/**
 * Open the Record sheet for a task by its exact label and submit an outcome.
 *
 * Taps the task row itself (SwipeTask.tsx: tapping the row calls onRecord()
 * directly when the swipe-actions aren't revealed) rather than going through
 * "More actions" → "Record" — that two-step swipe-reveal path uses a
 * JS-driven slide animation, and a scripted force-click can land on the
 * button's mid-animation (still off-screen) position instead of where it
 * ends up, clicking the wrong element. The row itself is never animated.
 */
export async function recordTask(page: Page, taskLabel: string, status: 'completed' | 'delayed' | 'skipped' | 'issue', note?: string) {
  const row = page.getByRole('button', { name: new RegExp(`^\\d+\\s+${escapeRegExp(taskLabel)}\\b`) });
  await row.scrollIntoViewIfNeeded();
  await row.click();
  await page.getByRole('radio', { name: status, exact: true }).click();
  if (note) await page.getByRole('textbox', { name: /observation.*reason/i }).fill(note);
  await page.getByRole('button', { name: 'Save task record', exact: true }).click();
  await page.waitForTimeout(500);
}

/**
 * ⚠️ Not currently used by the suite (not reliably stable yet — the first
 * medicine's status row starts pre-expanded, which this function accounts
 * for, but a later interaction still intermittently hangs; needs more work
 * before relying on it). Task 7 uses completeMedicationSupportViaApi()
 * instead. Left here as a starting point for someone adding dedicated
 * medication-support UI test coverage (it isn't one of the 7 usability
 * tasks, so wasn't in scope for this round).
 *
 * "Record medication support" doesn't open the generic task-outcome sheet —
 * it navigates to a dedicated Medication Support screen (MedicationEditor)
 * with a per-medicine Taken/Not Taken/Unable to Confirm choice plus an
 * overall outcome. recordTask() doesn't handle this task type.
 */
export async function recordMedicationSupport(page: Page, medicationStatus: 'Taken' | 'Not Taken' | 'Unable to Confirm' = 'Taken') {
  const row = page.getByRole('button', { name: /^\d+\s+Record medication support\b/ });
  await row.scrollIntoViewIfNeeded();
  await row.click();
  // Loop until no medicine still reads "Choose the observed status". The
  // first medicine starts pre-expanded (its status radios already visible)
  // — clicking its collapsed-trigger button would toggle it closed instead
  // of opening it, so only click the trigger when no radio group is
  // currently showing.
  while (await page.getByRole('button', { name: /Choose the observed status$/ }).count() > 0) {
    const statusRadio = page.getByRole('radio', { name: medicationStatus, exact: true }).first();
    if (!(await statusRadio.isVisible().catch(() => false))) {
      await page.getByRole('button', { name: /Choose the observed status$/ }).first().click();
    }
    await page.getByRole('radio', { name: medicationStatus, exact: true }).first().click();
  }
  await page.getByRole('radio', { name: 'Completed', exact: true }).click();
  await page.getByRole('button', { name: 'Review and save', exact: true }).click();
  await page.waitForTimeout(500);
}

/**
 * Report an issue on a task (the swipe action's "Issue" button, not
 * "Record"). There's no row-tap shortcut for this one (tapping the row
 * always calls onRecord()), so this goes through the swipe-reveal path:
 * "More actions" is a fixed-position button (safe to click immediately),
 * but the "Issue X" button it reveals slides in via a ~220ms JS-driven
 * animation — click it before that settles and Playwright clicks the
 * button's mid-animation (still off-screen) position. Wait for the
 * animation, then click normally (no force needed once it's settled).
 */
export async function reportTaskIssue(page: Page, taskLabel: string, issueType: string, note: string) {
  const moreActions = page.getByRole('button', { name: `More actions for ${taskLabel}`, exact: true });
  await moreActions.scrollIntoViewIfNeeded();
  await moreActions.click();
  await page.waitForTimeout(400); // let the swipe-reveal animation settle
  await page.getByRole('button', { name: `Report issue for ${taskLabel}`, exact: true }).click();
  await page.getByRole('radio', { name: issueType, exact: true }).click();
  await page.getByRole('textbox', { name: /observation.*reason/i }).fill(note);
  await page.getByRole('button', { name: 'Save task record', exact: true }).click();
  await page.waitForTimeout(500);
}

/**
 * True if a task still has an outstanding checklist row. Use this (not the
 * swipe-reveal "Record X" button's enabled state, which reads disabled in
 * the accessibility tree regardless of task state) to check whether a task
 * still needs recordTask() called on it.
 */
export async function isTaskPending(page: Page, taskLabel: string): Promise<boolean> {
  const row = page.getByRole('button', { name: new RegExp(`^\\d+\\s+${escapeRegExp(taskLabel)}\\b`) });
  return (await row.count()) > 0;
}
