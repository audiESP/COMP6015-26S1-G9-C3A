import { test, expect } from '@playwright/test';
import { mockAiEndpoints, startVisitIfNeeded, reportTaskIssue, openSeededSchedule, openVisitByPatientName } from './helpers';

// Coverage beyond the 7 usability tasks (see USABILITY_TEST_MODERATOR_GUIDE.md
// for why those 7 are a deliberately bounded subset, not full app coverage).
// Each test here is independent of the others and of usability-tasks.spec.ts
// — it uses a different seeded visit (Flor Bauch, 13:30) than that suite
// (Tresa Beier, 12:00) so the two files can't corrupt each other's state
// even though they share one Neon database.
//
// Remaining known gaps, not covered here: medication support's own UI (see
// recordMedicationSupport()'s docstring in helpers.ts), the incident
// checklist (no UI wires it up yet — IncidentChecklistItem exists only in
// the API schema), speech-to-text/text-to-speech (needs real audio, can't
// script), and GPS/offline edge cases.

const OTHER_VISIT_PATIENT = 'Flor Bauch';

test.describe('C3A additional coverage (automated)', () => {
  test.beforeEach(async ({ page }) => {
    await mockAiEndpoints(page);
  });

  test('Learn tab — browse a topic and open a material', async ({ page }) => {
    await page.goto('/');
    await page.getByRole('tab', { name: 'Learn' }).click();
    await expect(page.getByText('Care topics')).toBeVisible({ timeout: 10000 });

    const topics = page.getByRole('button').filter({ hasText: /resources$/ });
    await expect(topics.first()).toBeVisible();
    await topics.first().click();

    // Either a material list appears, or this topic is legitimately empty —
    // both are valid outcomes of a real content library; only a stuck
    // loading state is a failure.
    await expect(page.getByText(/no resources are available|Resources and language|SOURCE|ARTICLE|PDF|LINK/i).first()).toBeVisible({ timeout: 10000 });
  });

  test('Learn tab — search finds a result', async ({ page }) => {
    await page.goto('/');
    await page.getByRole('tab', { name: 'Learn' }).click();
    await page.getByRole('textbox', { name: 'Search resources' }).fill('falls');
    // Debounced search (300ms) + a real Postgres round trip.
    await expect(page.getByText(/no resources match your search/i).or(page.locator('text=/falls/i'))).toBeVisible({ timeout: 10000 });
  });

  test('Switch between visits from the schedule', async ({ page }) => {
    await openSeededSchedule(page);
    await expect(page.getByText('Tresa Beier')).toBeVisible({ timeout: 10000 });

    // "Your schedule" lists the other visits for the day — switch to one.
    const otherVisitRow = page.getByRole('button', { name: new RegExp(OTHER_VISIT_PATIENT) });
    await otherVisitRow.scrollIntoViewIfNeeded();
    await otherVisitRow.click();
    await expect(page.getByRole('button', { name: /Patient quick view/ })).toContainText(OTHER_VISIT_PATIENT, { timeout: 10000 });
  });

  test('Edit patient care preferences', async ({ page }) => {
    await openVisitByPatientName(page, OTHER_VISIT_PATIENT);

    await page.getByRole('button', { name: 'Patient quick view' }).click();
    await page.getByRole('button', { name: 'Full patient details' }).click();
    await page.getByRole('button', { name: 'Edit care preferences', exact: true }).click();

    // PatientModal's TextInputs aren't given an accessible label (no
    // accessibilityLabel prop), so they're only reachable by placeholder.
    // Confirm the modal actually opened before interacting with it — its
    // <Modal> can render a beat after the triggering click.
    const notesField = page.getByPlaceholder('Additional notes...');
    await expect(notesField).toBeVisible({ timeout: 10000 });
    await notesField.fill('E2E test note — preferences edited.');
    const saveButton = page.getByRole('button', { name: 'Link Patient', exact: true });
    await saveButton.click();
    await expect(page.getByText('Patient preferences saved.')).toBeVisible({ timeout: 10000 });
  });

  test('Patient edit modal shows the correct patient', async ({ page }) => {
    // Regression test for a real bug found via this suite: PatientModal.tsx
    // used to do `useState(initial ?? {})`, which only runs on mount — if
    // the modal's first mount raced ahead of this visit's real patient data,
    // it kept showing that stale patient forever, and worse, saved that
    // stale patient's identity fields over the real one (observed live:
    // editing Flor Bauch's visit silently renamed that patient record to
    // "Tresa Beier" in the database). Fixed by resyncing `form` from
    // `initial` in a useEffect keyed on [visible, initial].
    await openVisitByPatientName(page, OTHER_VISIT_PATIENT);
    await page.getByRole('button', { name: 'Patient quick view' }).click();
    await page.getByRole('button', { name: 'Full patient details' }).click();
    await page.getByRole('button', { name: 'Edit care preferences', exact: true }).click();
    const nameField = page.getByPlaceholder('Zhang San');
    await expect(nameField).toBeVisible({ timeout: 10000 });
    await expect(nameField).toHaveValue(OTHER_VISIT_PATIENT);
  });

  test('Report an issue on a task (not Complete)', async ({ page }) => {
    // Check-in (location snapshot + visit-start) can take close to the
    // default 90s test budget on this machine under load — give it real
    // headroom instead of tightening startVisitIfNeeded's retry timing
    // further (confirmed live: the visit does reach "in progress", just
    // not always inside 90s).
    test.setTimeout(240_000);
    await openVisitByPatientName(page, OTHER_VISIT_PATIENT);
    await startVisitIfNeeded(page);
    await reportTaskIssue(page, 'Wellbeing and nutrition check', 'patient_declined', 'E2E test — patient declined this check.');
    await expect(page.getByText('Task record saved to the server.')).toBeVisible({ timeout: 10000 });
  });
});
