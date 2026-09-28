#!/usr/bin/env python3
"""
Guardrail + correctness evaluation harness.

Loads each dataset referenced in questions.json (once per unique file),
asks each question through the live API, and checks the result against
its expectation type. Exits non-zero if anything fails, so it can also
run in CI as a smoke test (skipped there by default since it needs a
live LLM -- see .github/workflows/ci.yml).
"""
from __future__ import annotations
import argparse
import json
import os
import sys
import time

import requests

HERE = os.path.dirname(os.path.abspath(__file__))


def wait_for_job(base_url: str, job_id: str, timeout: int = 60) -> dict:
    start = time.time()
    while time.time() - start < timeout:
        r = requests.get(f"{base_url}/jobs/{job_id}")
        r.raise_for_status()
        job = r.json()
        if job["status"] in ("done", "failed"):
            return job
        time.sleep(0.5)
    raise TimeoutError(f"job {job_id} did not finish within {timeout}s")


def ingest(base_url: str, csv_path: str) -> str:
    with open(csv_path, "rb") as f:
        r = requests.post(f"{base_url}/ingest", files={"file": (os.path.basename(csv_path), f, "text/csv")})
    r.raise_for_status()
    job = wait_for_job(base_url, r.json()["job_id"])
    if job["status"] != "done":
        raise RuntimeError(f"ingest failed: {job.get('error')}")
    return job["result"]["dataset_id"]


def ask(base_url: str, dataset_id: str, question: str) -> dict:
    r = requests.post(f"{base_url}/query", json={"dataset_id": dataset_id, "question": question})
    r.raise_for_status()
    job = wait_for_job(base_url, r.json()["job_id"])
    if job["status"] != "done":
        return {"answerable": False, "refusal_reason": f"job failed: {job.get('error')}"}
    return job["result"]


def check(expect: dict, result: dict) -> tuple[bool, str]:
    etype = expect["type"]
    if etype == "refusal":
        ok = result.get("answerable") is False
        return ok, "expected a refusal" if not ok else "ok"
    if etype == "answerable":
        ok = result.get("answerable") is True and result.get("rows")
        return bool(ok), "expected an answer with rows" if not ok else "ok"
    if etype == "exact_value":
        ok = (
            result.get("answerable") is True
            and result.get("rows")
            and len(result["rows"]) == 1
            and len(result["rows"][0]) == 1
            and int(result["rows"][0][0]) == int(expect["value"])
        )
        got = result.get("rows")
        return bool(ok), f"expected {expect['value']}, got {got}" if not ok else "ok"
    return False, f"unknown expectation type {etype}"


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--base-url", default="http://localhost:8000")
    parser.add_argument("--questions", default=os.path.join(HERE, "questions.json"))
    args = parser.parse_args()

    with open(args.questions) as f:
        cases = json.load(f)

    dataset_ids: dict[str, str] = {}
    passed, failed = 0, 0

    for case in cases:
        csv_path = os.path.join(HERE, "..", case["dataset"])
        if csv_path not in dataset_ids:
            print(f"Ingesting {case['dataset']} ...")
            dataset_ids[csv_path] = ingest(args.base_url, csv_path)

        dataset_id = dataset_ids[csv_path]
        result = ask(args.base_url, dataset_id, case["question"])
        ok, detail = check(case["expect"], result)
        status = "PASS" if ok else "FAIL"
        print(f"[{status}] {case['id']}: {case['question']!r} -> {detail}")
        passed += ok
        failed += not ok

    print(f"\n{passed} passed, {failed} failed out of {len(cases)}")
    sys.exit(1 if failed else 0)


if __name__ == "__main__":
    main()
