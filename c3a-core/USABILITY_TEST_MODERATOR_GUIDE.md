# C3A Usability Test — Moderator Guide (v2)

Companion to `Participant_Consent_Form.pdf` and `Questionnaire.pdf` (or the
simplified student-pilot versions — see `PILOT_QUESTIONNAIRE_NOTES.md`). This
file is for whoever runs the session — not shown to the participant.

**Changes in this version, per supervisor feedback:**
1. Tasks now map one-to-one to each team member's own feature (patient
   summary, task-linked training materials), not just the shared visit flow.
2. AI generation time is recorded separately from the participant's own
   operating time, so the result measures the UI, not model speed.
3. Qdrant must be confirmed reachable before a session counts as valid.
4. The student-pilot demographic questions and consent wording are kept in
   a separate note so the original HREC-targeted documents stay untouched.

One known gap that **cannot** be tested: an earlier "undo a completed task"
feature was removed from the codebase during a later UI redesign and no
longer exists in the current build — do not script it, and say so plainly
in the report rather than treating it as a missed test.

## Before each session (all four are blocking — do not start without them)

- [ ] AI layer, API gateway, and Ollama are running — `GET /health` and
      `GET /ai/health` both return 200.
- [ ] **Qdrant is confirmed reachable, not just "running."** Call
      `POST /ai/rag/search {"query":"falls prevention"}` directly against the
      AI service and check `status.status == "configured"` with
      `results` non-empty, or check `GET /ai/health` →
      `rag.status == "configured"` with `last_error: null`. If it's still
      down, do not run the session as a result you'll report — Task 4's
      answer will cite patient records only (no guideline source), and Task
      3's recommended materials will silently become 100% web search
      instead of the project's own material library. Either fix Qdrant
      first or run the session as an explicitly-labelled degraded-mode
      pilot, not as a counted data point.
- [ ] **Reset the demo data.** Task 2 and Task 7 mutate the seeded visits.
      Re-run `c3a-core-api/migrations/002_seed_demo_operational_data.sql`
      against Neon before every participant, not just the first.
- [ ] Device signed into worker `cw-001`, visit date set to **2026-09-04**.

## Session flow

1. Consent first (signature on the Consent Form, or verbal consent per the
   student-pilot wording — see `PILOT_QUESTIONNAIRE_NOTES.md`).
2. Think-aloud framing: "Please talk through what you're thinking as you go
   — I'm testing the app, not you."
3. Run the seven tasks below in order, reading each **prompt** verbatim.
   Only help if they're stuck for more than ~60 seconds of active operating
   time (not counting time spent waiting on the AI) — and if you do help,
   mark that task as assisted, not an unassisted pass.
4. Hand over the Questionnaire for them to complete alone.
5. Thank them, give the voucher, offer the optional follow-up.

## Timing rule: operating time vs. AI wait time

For any task that calls the AI (Tasks 1, 4, 7 below), **stop your operating
clock the instant they tap "generate / send / confirm" and start a separate
AI-wait clock**, then resume the operating clock the instant content appears
and they resume interacting. Record both.

- **Operating time** = time the participant is actively deciding/navigating.
  This is the usability metric.
- **AI wait time** = time spent waiting on a model response. This is a
  system-performance metric (and doubles as the "response speed" figure your
  supervisor asked for) — report it separately, e.g. "median AI wait time
  for patient summary: 74s."
- The **3-minute task-failure cutoff applies to operating time only.** A
  task isn't a failure because the model was slow; it's a failure if the
  participant couldn't figure out what to do.

## Tasks

### Task 1 — View the patient summary before starting care (NEW — FR3)

**Prompt:** "Before you start caring for this patient today, check whether
they have any known allergies and what medications they're on."

Expected path: tap the patient card at the top of the visit screen → patient
quick-view sheet → "Full patient details" → patient page shows the
AI-generated summary (auto-loads; this is the AI wait — time it separately).

**Success:** participant finds the summary unprompted and can correctly say
whether the patient has any recorded allergies (there may be none — "no
known allergies" stated correctly also counts as success) and name at least
one medication.

### Task 2 — Check in to a visit and record care tasks in any order

**Prompt:** "Start today's first visit, check in, then record today's lunch
task and mobility task — in whichever order makes sense to you, not
necessarily the order they're listed."

Expected path: Visits tab → first scheduled visit → Start visit → confirm
identity → check in → on the checklist, swipe and record the lunch task and
the mobility task in participant-chosen order (nothing in the UI enforces
sequence — this is intentional, confirm they aren't blocked either way).

**Note (confirmed while building the automated test for this task):**
checking the identity box and checking in auto-completes "Arrive and confirm
identity" — it never appears as a separate row to record. Progress reads
"1 / 6" immediately after check-in. Don't prompt the participant to record
it separately; if they go looking for it, that's worth noting as confusion
about scope (one task fewer than the visible "6 tasks" implies at a glance).

**Success:** both remaining tasks reach completed status regardless of the
order chosen, and the participant isn't confused by being able to skip
ahead.

### Task 3 — Open the training material recommended for a task

**Prompt:** "You're about to help this patient with lunch. Find a reference
related to that specific task — not a general search, something linked to
the task itself."

Expected path: on the care checklist, under the lunch/meal task, open the
"Training material" expander → review the returned material(s).

**Success:** they open the per-task recommendation (the expander under the
task card), not the separate Learn tab's topic search. If they go to Learn
first, let them discover it's the wrong spot and self-correct — note that as
one wrong turn, not an assist, if they get there unprompted.

### Task 4 — Ask a care question and find its cited source

**Prompt:** "Ask the assistant a question about this patient's care, the way
you would if you needed a quick answer during a visit. Then tell me which
source it says the answer came from."

Expected path: Assistant tab → ask a question → send (start AI-wait clock)
→ reply appears (resume operating clock) → read the "Sources used" section
under the reply and name one.

**Correction (found while building the automated test for this task):**
citations in the chat reply are plain text, not a tappable element — there
is no "open" action to drill into a source from the chat screen (unlike the
per-task recommended materials in Task 3, where a web source is a real
clickable link). The original wording of this task asked participants to
"open" a source, which isn't something the current build supports — don't
script an action that doesn't exist.

**Success:** they locate the "Sources used" section unprompted and can read
back which source it names. If Qdrant was down for this session, a
guideline citation may not be available — note that explicitly rather than
scoring it as a UI failure.

### Task 5 — Translate a care instruction

**Prompt:** "Translate this instruction for the patient: 'Please take this
tablet after lunch with a full glass of water.'"

Expected path: Translate tab → enter text → confirm target language →
translation appears.

**Success:** a translated result is displayed.

### Task 6 — Review a risk alert and record an action

**Prompt:** "There's an open alert for this visit. Open it, decide on an
action, and record it."

Expected path: tap the alert banner → Risks page → select alert → "Review
and record action" → choose acknowledge/resolve → note → save.

**Success:** the alert's status changes and a note was recorded.

### Task 7 — Generate a visit report

**Prompt:** "You're finishing this visit. Complete the remaining tasks, fill
in the outcome form, and generate the visit report."

Expected path: complete remaining tasks → "Care outcomes and report" →
step through the 4-step form → generate report (start AI-wait clock) →
report appears (resume) → confirm and finish.

**Success:** a report is generated and the visit reaches completed state.

## Moderator observation sheet

| Participant code | Task | Operating time | AI wait time (N/A if none) | Completed unassisted? (Y/Partial/N) | # wrong turns | Assist given? | Notes |
|---|---|---|---|---|---|---|---|
| | 1. Patient summary | | | | | | |
| | 2. Check in + tasks any order | | — | | | | |
| | 3. Open task-linked material | | — | | | | |
| | 4. Ask question + open source | | | | | | |
| | 5. Translate | | — | | | | |
| | 6. Review alert + record action | | — | | | | |
| | 7. Generate report | | | | | | |

"Wrong turn" = any tap that doesn't move toward the goal (wrong tab, back
out of a flow, swipe the wrong way). Count them even if the task eventually
succeeds — this is what supports a claim like "3 of 5 participants opened
the Learn tab before finding the task-linked material in Task 3."

## After all sessions

- **Task success rate** per task (unassisted Y vs. Partial/N/assisted).
- **Operating-time** median/range per task — the usability number.
- **AI-wait-time** median/range per task — the performance number, reported
  separately, explicitly noting the 8GB test machine's memory constraints
  as a caveat (see `FUNCTIONAL_TEST_RESULTS.md`) so slow local hardware
  isn't read as a product problem.
- **SUS score**: sum the 10 items after reverse-scoring the even-numbered
  (negatively worded) ones, × 2.5. Report mean + individual scores — 68 is
  "average" on the published norm, so state that for context.
- **Qualitative themes** from free-text answers and verbatim notes, grouped
  by repeated pain point rather than listed one by one.
- State plainly which tasks ran with Qdrant down, if any, and exclude or
  flag those citation-related results separately.
