"""Run 180 cases from isolated cloud PostgreSQL fixtures and remove every fixture.

Only the UUIDs in the case file may be inserted. All writes are tagged with a
unique import batch ID. A uniquely named cloud table holds the complete case
requests; it is dropped during cleanup. Synthea patient/CALD/medicine/allergy rows are updated to mirror each
non-control request before the AI endpoint is called. No existing patient row
is updated. The finally block cleans the batch; --cleanup-manifest recovers
from an interrupted process that could not run its finally block.
"""

from __future__ import annotations

import argparse
import copy
import json
import time
from datetime import datetime, timezone
from pathlib import Path
from uuid import uuid4

import psycopg
import requests
from dotenv import dotenv_values
from psycopg import sql
from psycopg.types.json import Jsonb

from run_cases import load_cases, run_units


HERE = Path(__file__).resolve().parent


def database_url() -> str:
    value = dotenv_values(HERE.parent / ".env").get("DATABASE_URL")
    if not value:
        raise RuntimeError("DATABASE_URL is absent from c3a-core-ai/.env")
    return value


def save_manifest(path: Path, data: dict) -> None:
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def fixture_ids(cases: list[dict], expected_count: int = 36) -> list[str]:
    ids = {case["request"]["patientContext"]["id"] for case in cases if case["request"].get("patientContext")}
    if len(ids) != expected_count:
        raise ValueError(f"Expected {expected_count} distinct test patient IDs, got {len(ids)}")
    return sorted(ids)


def create_fixtures(conn: psycopg.Connection, cases: list[dict], batch_id: str, case_table: str,
                    expected_patient_count: int = 36) -> list[str]:
    ids = fixture_ids(cases, expected_patient_count)
    baseline = {case["seed_id"]: case for case in cases if case["condition"] == "A"}
    with conn.cursor() as cur:
        cur.execute("SELECT id FROM c3a_synthea_patients WHERE id = ANY(%s::uuid[])", (ids,))
        collisions = cur.fetchall()
        if collisions:
            raise RuntimeError(f"Fixture UUID collision: {len(collisions)} IDs already exist")
        cur.execute("INSERT INTO c3a_synthea_import_batches (id,source,synthea_seed,reference_date,notes) VALUES (%s,%s,%s,%s,%s)",
                    (batch_id, "c3a-evaluation", 6015, datetime.now(timezone.utc).date(), "Isolated 180-case context evaluation; remove after run"))
        for case in baseline.values():
            patient = case["request"]["patientContext"]
            cur.execute(
                "INSERT INTO c3a_synthea_patients (id,import_batch_id,birthdate,age,first_name,last_name,source_payload) VALUES (%s,%s,%s,%s,%s,%s,%s)",
                (patient["id"], batch_id, "1946-01-01", patient.get("age") or 80,
                 patient.get("name") or "Evaluation Patient", "", Jsonb({"evaluation_batch": batch_id})),
            )
        cur.execute(sql.SQL("CREATE TABLE {} (case_id text PRIMARY KEY, case_spec jsonb NOT NULL)").format(sql.Identifier(case_table)))
        for case in cases:
            cur.execute(sql.SQL("INSERT INTO {} (case_id,case_spec) VALUES (%s,%s)").format(sql.Identifier(case_table)),
                        (case["case_id"], Jsonb(case)))
    conn.commit()
    return ids


def apply_case(conn: psycopg.Connection, case: dict, batch_id: str) -> dict:
    patient = case["request"].get("patientContext")
    if not patient:
        return {"control_context_omitted": True}
    patient_id = patient["id"]
    name = patient.get("name") or "Evaluation Patient"
    medications = list(patient.get("medications") or [])
    allergies = list(patient.get("allergies") or [])
    with conn.cursor() as cur:
        cur.execute("SELECT import_batch_id FROM c3a_synthea_patients WHERE id=%s FOR UPDATE", (patient_id,))
        row = cur.fetchone()
        if row != (batch_id,):
            raise RuntimeError(f"Patient {patient_id} does not belong to the evaluation batch")
        cur.execute(
            "UPDATE c3a_synthea_patients SET first_name=%s,last_name='',age=%s,source_payload=%s WHERE id=%s AND import_batch_id=%s",
            (name, patient.get("age") or 80, Jsonb({"evaluation_batch": batch_id, "request_patient": patient}), patient_id, batch_id),
        )
        cur.execute("DELETE FROM c3a_synthea_cald_profiles WHERE patient_id=%s", (patient_id,))
        if patient.get("interpreterRequired") is not None:
            cur.execute(
                """INSERT INTO c3a_synthea_cald_profiles
                (patient_id,preferred_language,interpreter_required,cultural_background,mobility_support,cognitive_status,dietary_notes,communication_notes,care_risk_flags,profile_payload)
                VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)""",
                (patient_id, patient.get("preferredLanguage") or "Unknown", patient["interpreterRequired"],
                 patient.get("culturalBackground"), patient.get("mobilitySupport"), patient.get("cognitiveStatus"),
                 patient.get("dietaryNotes"), patient.get("communicationNotes"),
                 Jsonb(patient.get("careRiskFlags") or []), Jsonb({"evaluation_batch": batch_id})),
            )
        cur.execute("DELETE FROM c3a_synthea_medications WHERE patient_id=%s", (patient_id,))
        for medicine in medications:
            cur.execute("INSERT INTO c3a_synthea_medications (patient_id,description) VALUES (%s,%s)", (patient_id, medicine))
        cur.execute("DELETE FROM c3a_synthea_allergies WHERE patient_id=%s", (patient_id,))
        for allergy in allergies:
            cur.execute("INSERT INTO c3a_synthea_allergies (patient_id,description,source_payload) VALUES (%s,%s,%s)",
                        (patient_id, allergy, Jsonb({"evaluation_batch": batch_id})))
    conn.commit()
    with conn.cursor() as cur:
        cur.execute("SELECT first_name,age FROM c3a_synthea_patients WHERE id=%s AND import_batch_id=%s", (patient_id, batch_id))
        stored_patient = cur.fetchone()
        cur.execute("SELECT mobility_support,preferred_language,interpreter_required,communication_notes,dietary_notes,cognitive_status,care_risk_flags FROM c3a_synthea_cald_profiles WHERE patient_id=%s", (patient_id,))
        stored_cald = cur.fetchone()
        cur.execute("SELECT description FROM c3a_synthea_medications WHERE patient_id=%s ORDER BY description", (patient_id,))
        stored_medications = [item[0] for item in cur.fetchall()]
        cur.execute("SELECT description FROM c3a_synthea_allergies WHERE patient_id=%s ORDER BY description", (patient_id,))
        stored_allergies = [item[0] for item in cur.fetchall()]
    if stored_patient != (name, patient.get("age") or 80):
        raise RuntimeError("Cloud patient readback mismatch")
    if patient.get("interpreterRequired") is None:
        if stored_cald is not None:
            raise RuntimeError("Cloud CALD readback should be absent")
    elif stored_cald != (patient.get("mobilitySupport"), patient.get("preferredLanguage") or "Unknown",
                          patient["interpreterRequired"], patient.get("communicationNotes"),
                          patient.get("dietaryNotes"), patient.get("cognitiveStatus"),
                          patient.get("careRiskFlags") or []):
        raise RuntimeError("Cloud CALD readback mismatch")
    if stored_medications != sorted(medications) or stored_allergies != sorted(allergies):
        raise RuntimeError("Cloud medication/allergy readback mismatch")
    return {"patient_row": 1, "cald_row": int(stored_cald is not None),
            "medication_rows": len(stored_medications), "allergy_rows": len(stored_allergies)}


def cleanup(batch_id: str, ids: list[str], case_table: str, connection_url: str) -> dict:
    # Batch ownership and the exact UUID list limit this delete to our fixtures.
    if not case_table.startswith("c3a_eval_cases_"):
        raise ValueError("Refusing cleanup for an unexpected case table name")
    with psycopg.connect(connection_url, connect_timeout=10) as conn:
        with conn.cursor() as cur:
            cur.execute(sql.SQL("DROP TABLE IF EXISTS {}").format(sql.Identifier(case_table)))
            cur.execute("DELETE FROM c3a_synthea_patients WHERE import_batch_id=%s AND id = ANY(%s::uuid[]) RETURNING id", (batch_id, ids))
            deleted = len(cur.fetchall())
            cur.execute("DELETE FROM c3a_synthea_import_batches WHERE id=%s", (batch_id,))
            cur.execute("SELECT COUNT(*) FROM c3a_synthea_patients WHERE import_batch_id=%s OR id = ANY(%s::uuid[])", (batch_id, ids))
            remaining = cur.fetchone()[0]
            if remaining:
                raise RuntimeError(f"Fixture cleanup incomplete: {remaining} patient rows remain")
            cur.execute("SELECT to_regclass(%s)", (f"public.{case_table}",))
            if cur.fetchone()[0] is not None:
                raise RuntimeError("Evaluation case table remains after cleanup")
        conn.commit()
    return {"deleted_patient_rows": deleted, "remaining_patient_rows": 0, "case_table_removed": True}


def run(args: argparse.Namespace) -> None:
    if args.output is None or args.manifest is None:
        raise ValueError("--output and --manifest are required for a cloud run")
    all_cases = load_cases(args.cases)
    if len(all_cases) != 180:
        raise ValueError("The source case file must contain exactly 180 cases")
    if args.case_ids_file:
        selected_ids = set(json.loads(args.case_ids_file.read_text()))
        known_ids = {case["case_id"] for case in all_cases}
        if not selected_ids or selected_ids - known_ids:
            raise ValueError("Case selection is empty or contains unknown IDs")
        selected = [case for case in all_cases if case["case_id"] in selected_ids]
        prerequisite_ids = {
            case["case_id"] for case in all_cases
            if case["condition"] == "multiturn" and any(
                chosen["condition"] == "multiturn" and
                chosen["sequence_id"] == case["sequence_id"] and
                chosen["turn"] >= case["turn"] for chosen in selected
            )
        }
        cases = [case for case in all_cases if case["case_id"] in selected_ids | prerequisite_ids]
        seed_ids = {case["seed_id"] for case in cases}
        baselines = [case for case in all_cases if case["condition"] == "A" and case["seed_id"] in seed_ids]
        fixture_cases = baselines + [case for case in cases if case["case_id"] not in {item["case_id"] for item in baselines}]
        expected_patient_count = len(seed_ids)
    elif args.multiturn_only:
        cases = [case for case in all_cases if case["condition"] == "multiturn"]
        seed_ids = {case["seed_id"] for case in cases}
        baselines = [case for case in all_cases if case["condition"] == "A" and case["seed_id"] in seed_ids]
        if len(cases) != 36 or len(seed_ids) != 12 or len(baselines) != 12:
            raise ValueError("Expected 12 three-turn sequences and 12 baselines")
        fixture_cases = baselines + cases
        expected_patient_count = 12
    else:
        cases = all_cases
        fixture_cases = all_cases
        expected_patient_count = 36
    units = run_units(cases, args.seed)
    ids = fixture_ids(fixture_cases, expected_patient_count)
    print(f"Validated {len(cases)} cases and {len(ids)} new cloud patient UUIDs", flush=True)
    if not args.execute:
        print("Dry run: no cloud writes or AI calls", flush=True)
        return
    if args.output.exists() or args.manifest.exists():
        raise SystemExit("Refusing to overwrite output or manifest")
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.manifest.parent.mkdir(parents=True, exist_ok=True)
    batch_id = f"c3a-eval-{len(cases)}-{datetime.now(timezone.utc):%Y%m%dT%H%M%SZ}-{uuid4().hex[:8]}"
    case_table = "c3a_eval_cases_" + batch_id.rsplit("-", 1)[-1]
    manifest = {"batch_id": batch_id, "patient_ids": ids, "case_count": len(cases),
                "stored_case_specs": len(fixture_cases), "mode": "multiturn_only" if args.multiturn_only else "full",
                "case_table": case_table, "case_ids_file": str(args.case_ids_file) if args.case_ids_file else None,
                "status": "preparing", "started_at": datetime.now(timezone.utc).isoformat(),
                "database_source": "c3a-core-ai/.env DATABASE_URL", "output": str(args.output)}
    save_manifest(args.manifest, manifest)
    connection_url = database_url()
    created = False
    run_error = None
    try:
        with psycopg.connect(connection_url, connect_timeout=10) as conn:
            create_fixtures(conn, fixture_cases, batch_id, case_table, expected_patient_count)
            created = True
            manifest["status"] = "running"
            save_manifest(args.manifest, manifest)
            completed = 0
            with args.output.open("x", encoding="utf-8") as stream:
                for unit in units:
                    if args.limit and completed >= args.limit:
                        break
                    history = []
                    for stub in unit:
                        if args.limit and completed >= args.limit:
                            break
                        with conn.cursor() as cur:
                            cur.execute(sql.SQL("SELECT case_spec FROM {} WHERE case_id=%s").format(sql.Identifier(case_table)), (stub["case_id"],))
                            case = cur.fetchone()[0]
                        cloud_readback = apply_case(conn, case, batch_id)
                        request = copy.deepcopy(case["request"])
                        if case["condition"] == "multiturn":
                            request["messages"] = history + request["messages"]
                        started = time.monotonic()
                        result = {"case_id": case["case_id"], "seed_id": case["seed_id"],
                                  "domain": case["domain"], "condition": case["condition"],
                                  "sequence_id": case.get("sequence_id"), "turn": case.get("turn"),
                                  "recorded_at": datetime.now(timezone.utc).isoformat(),
                                  "request": request, "cloud_fixture": cloud_readback,
                                  "batch_id": batch_id}
                        try:
                            response = requests.post(args.endpoint, json=request, timeout=args.timeout)
                            result["http_status"] = response.status_code
                            if response.ok:
                                result["response"] = response.json()
                                if case["condition"] == "multiturn":
                                    history = request["messages"] + [{"role": "assistant", "content": result["response"]["reply"]}]
                            else:
                                result["error"] = response.text[:500]
                        except requests.RequestException as exc:
                            result["error"] = f"{type(exc).__name__}: {str(exc)[:200]}"
                        result["elapsed_seconds"] = round(time.monotonic() - started, 2)
                        stream.write(json.dumps(result, ensure_ascii=False) + "\n")
                        stream.flush()
                        completed += 1
                        print(f"{completed}/{len(cases)} {case['case_id']} HTTP {result.get('http_status')} error {result.get('error')}", flush=True)
                        if "error" in result and case["condition"] == "multiturn":
                            break
            manifest["completed_requests"] = completed
    except BaseException as exc:
        run_error = f"{type(exc).__name__}: {str(exc)[:300]}"
        manifest["run_error"] = run_error
        raise
    finally:
        if created:
            try:
                manifest["cleanup"] = cleanup(batch_id, ids, case_table, connection_url)
                manifest["status"] = "cleaned" if run_error is None else "interrupted_and_cleaned"
            except Exception as exc:
                manifest["cleanup_error"] = f"{type(exc).__name__}: {str(exc)[:300]}"
                manifest["status"] = "cleanup_failed"
        if not created:
            manifest["status"] = "rolled_back_before_commit"
        save_manifest(args.manifest, manifest)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--cases", type=Path, default=HERE / "cases.jsonl")
    parser.add_argument("--seed", type=int, default=6015)
    parser.add_argument("--endpoint", default="http://127.0.0.1:8001/ai/chat")
    parser.add_argument("--timeout", type=float, default=300)
    parser.add_argument("--output", type=Path)
    parser.add_argument("--manifest", type=Path)
    parser.add_argument("--execute", action="store_true")
    parser.add_argument("--limit", type=int, default=0, help="Positive count for fixture/cleanup preflight; zero runs all 180")
    parser.add_argument("--multiturn-only", action="store_true", help="Run only 12 three-turn sequences (36 requests) using 12 new cloud patients")
    parser.add_argument("--case-ids-file", type=Path, help="JSON list of case IDs to rerun; earlier turns of selected multi-turn cases are added")
    parser.add_argument("--cleanup-manifest", type=Path)
    args = parser.parse_args()
    if args.cleanup_manifest:
        manifest = json.loads(args.cleanup_manifest.read_text(encoding="utf-8"))
        manifest["cleanup"] = cleanup(manifest["batch_id"], manifest["patient_ids"], manifest["case_table"], database_url())
        manifest["status"] = "cleaned"
        save_manifest(args.cleanup_manifest, manifest)
        print(manifest["cleanup"])
        return
    run(args)


if __name__ == "__main__":
    main()
