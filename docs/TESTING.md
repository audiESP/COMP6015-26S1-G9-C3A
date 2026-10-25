# Testing & Quality

This guide separates deterministic software tests from probabilistic AI
evaluation. Passing the tests does not establish clinical safety.

## 1. Test matrix

| Area | Location | What it covers | External dependency |
|---|---|---|---|
| API unit/contract | `c3a-core-api/tests` | chat source forwarding, checklist/location/medication rules, visit/alert access, schema contracts | Mostly mocked |
| PostgreSQL integration | `c3a-core-api/tests` | persisted risk lifecycle, locations, medication audit, training-resource migrations | Opt-in test database |
| AI unit/contract | `c3a-core-ai/tests` | router, orchestration, current-record responses, prompts, Qdrant client lifecycle, speech, risk parsing, web filtering | Mostly mocked; installed packages required |
| Frontend static check | `c3a-core-ui` | strict TypeScript compilation | Node modules |
| AI case validation | `c3a-core-ai/evaluation` | structure/pairing of 180 synthetic cases | None |
| AI live evaluation | `c3a-core-ai/evaluation` | 180 endpoint responses across six domains and five conditions | Running AI stack; optional cloud fixtures |

There is currently no committed frontend unit/component/E2E suite, no lint
script, no coverage threshold, and no CI workflow in the repository.

## 2. Standard local checks

Run these from an activated environment with both requirements files installed:

```powershell
Set-Location c3a-core\c3a-core-api
python -m unittest discover -s tests -v

Set-Location ..\c3a-core-ai
python -m unittest discover -s tests -v

Set-Location ..\c3a-core-ui
npx tsc --noEmit

Set-Location ..\c3a-core-ai
python evaluation\validate_cases.py
python evaluation\run_cases.py
```

The last command is a dry run unless `--execute` is supplied.

## 3. PostgreSQL integration tests

Use a dedicated test database or a reviewed development database. Although the
tests use transactions/separate schemas where implemented, never point them at
production data.

```powershell
$env:RUN_POSTGRES_INTEGRATION_TESTS = '1'
Set-Location c3a-core\c3a-core-api
python -m unittest discover -s tests -p 'test_postgres_fr6_integration.py' -v
python -m unittest discover -s tests -p 'test_training_resources.py' -v
```

Unset the switch afterwards:

```powershell
Remove-Item Env:RUN_POSTGRES_INTEGRATION_TESTS
```

## 4. AI evaluation design

`cases.jsonl` contains 180 synthetic request specifications:

- six domains, 30 cases each: mobility, medication support, risk state,
  workflow state, communication, and identity/missing data;
- 36 baseline `A`, 36 relevant-change `B`, 36 irrelevant-change `C`, and 36
  context-omitted controls;
- 12 three-turn sequences, totalling 36 multi-turn requests;
- a fixed shuffle seed of `6015` by default.

Validate and preview without network traffic:

```powershell
Set-Location c3a-core\c3a-core-ai
python evaluation\validate_cases.py
python evaluation\run_cases.py
```

Run against a local AI service only when an output path has been chosen:

```powershell
python evaluation\run_cases.py --execute `
  --endpoint http://127.0.0.1:8001/ai/chat `
  --output evaluation\results\local-run.jsonl
```

The runner refuses to overwrite an existing result. `run_cloud_cases.py`
creates and later removes isolated PostgreSQL fixtures; preserve its cleanup
manifest, and use `--cleanup-manifest` after an interrupted run. Read that
script before execution because it writes to the configured cloud database.

The repository also contains local Llama judging and blinded review-packet
tools. Model judging is useful for regression triage but cannot replace a
clinician/domain-expert review. Using the same model family as generator and
judge creates correlated errors and previously produced false negatives.

## 5. Verification snapshot — 20 October 2026

Checks executed in the current workspace:

| Check | Result |
|---|---|
| API `unittest` discovery | 52 tests: 41 passed, 11 PostgreSQL tests skipped, 0 failures |
| AI `unittest` discovery | 67 tests: 66 passed, 1 environment error |
| Frontend `npx tsc --noEmit` | Passed |
| Evaluation case validation | Passed: 180 unique cases, 36 triplets, 36 controls, 12 three-turn sequences |
| Evaluation dry run | Passed: 180 cases in 156 execution units; no HTTP requests sent |

The AI error was `ModuleNotFoundError: qdrant_client` in
`test_qdrant_store.py`; the test host had not installed the AI requirements.
Install `c3a-core-ai/requirements.txt` in the selected virtual environment and
rerun before treating the suite as green. A FastAPI/Starlette deprecation
warning about the test client was also emitted and should be addressed during
the next dependency upgrade.

The integration tests were intentionally not run because they require an
explicit database target. No live Ollama, Qdrant, Tavily, speech, or Expo E2E
test was performed in this documentation pass.

## 6. Findings from the project AI evaluation

The checked-in evaluation/report tooling records that the full synthetic run
returned HTTP 200 for all 180 requests and that the targeted stale multi-turn
current-record path was repaired for its 24 update follow-ups. These are
engineering observations, not clinical validation. The report logic also
identifies remaining failure families:

- a listed medicine can be over-interpreted as one the patient is taking, and
  declined support can be over-interpreted as proof that none was administered;
- missing patient context can be presented as a definite negative or replaced
  by invented patient-specific facts;
- interpreter requirements/unknown flags can be omitted or overstated;
- retrieved material can be only partially relevant to the generated advice;
- the repaired path states the current structured value but cannot prove the
  exact difference from an earlier structured record, because only the current
  snapshot is supplied.

Raw historical response and judge files are ignored under
`evaluation/results/` and are not present in this checkout. Therefore, report
templates alone are insufficient to independently reproduce numeric scores.
A formal release should archive sanitised raw results, manifests, hashes,
model digests, dependency versions, and an immutable Qdrant snapshot.

## 7. Known issues and quality risks

| Priority | Issue | Effect / required action |
|---|---|---|
| Critical | Credentials existed in tracked files/history | Rotate all affected secrets; consider repository history rewrite and notify collaborators. |
| Critical | Prototype has no real authentication and permissive CORS | Do not expose publicly or use real patient data; add identity, session, TLS, and origin controls first. |
| High | AI is not clinically validated and still has documented fact/uncertainty/evidence errors | Require human review; expand domain-expert evaluation and safety cases. |
| High | `/upload` stores files in `/tmp` without serving/cleanup policy | Disable or redesign with validation, bounded retention, access control, and deletion. |
| High | Default Llama configuration is text-only while UI accepts attachments | Reject clearly in UI or add a reviewed multimodal pipeline. |
| High | Raw SQL migrations have no ledger; seed/catalogue migrations contain deletes | Use a disposable database, backups, review, and recorded sequencing. |
| Medium | Python dependencies are range-based, not locked | Produce a lock/constraints file or container images for formal releases. |
| Medium | Frontend lacks automated behaviour/E2E tests | Add tests for visit mutations, offline/errors, permissions, attachments, and accessibility. |
| Medium | Historical evaluation outputs and source PDFs are absent | Archive versioned, licensed inputs and sanitised outputs with checksums. |
| Medium | Chat is memory-only and `/upload` URLs are not retrievable | Document as ephemeral or implement deliberate persistence/storage. |
| Medium | Fixed demo visits are dated `2026-09-04` | Set `EXPO_PUBLIC_SHIFT_DATE` or generate date-relative seed data. |
| Low | Test client emits a dependency deprecation warning | Pin compatible versions and migrate before the deprecated path is removed. |

## 8. Release quality gate

Before tagging a research/demo release:

1. start from a clean clone and a fresh virtual environment;
2. record OS, Python, Node/npm, Ollama/model digest, embedding model, PostgreSQL
   schema revision, and Qdrant snapshot;
3. run all unit/type checks with zero unexpected skips/errors;
4. run integration tests against a disposable database and confirm cleanup;
5. run representative UI flows on every target platform;
6. run the AI regression set and have safety-critical failures reviewed by an
   independent domain expert;
7. secret-scan the working tree and Git history;
8. verify that distributed artefacts contain only synthetic/sanitised data.

