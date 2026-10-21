"""
End-to-End Automated Demonstration Runner for INTELISE Component 4.
Executes Scenarios A, B, and C against the active backend server and Docker sandbox.
Collects deterministic execution logs, defect reports, governance decisions, and XAI packages.
"""
import os
import sys
import json
import time
import requests

# Ensure UTF-8 output on Windows consoles
if sys.platform == "win32":
    sys.stdout.reconfigure(encoding="utf-8")
    sys.stderr.reconfigure(encoding="utf-8")

BACKEND_URL = "http://127.0.0.1:8000"
SCENARIOS_DIR = os.path.dirname(os.path.abspath(__file__))

def print_header(title):
    print("\n" + "=" * 70)
    print(f" {title} ")
    print("=" * 70)

def get_delivery_auth_token():
    """Retrieve delivery authorization token from environment or backend/.env without exposing it."""
    token = os.environ.get("DELIVERY_AUTH_TOKEN")
    if token and token.strip():
        return token.strip()
    
    # Try reading from backend/.env
    env_file = os.path.normpath(os.path.join(SCENARIOS_DIR, "..", "backend", ".env"))
    if os.path.exists(env_file):
        with open(env_file, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if line.startswith("DELIVERY_AUTH_TOKEN="):
                    val = line.split("=", 1)[1].strip().strip('"').strip("'")
                    if val:
                        return val
    return None

def wait_for_run_completion(run_id, max_seconds=45):
    """Polls until verification run status is terminal (PASSED, FAILED, ERROR)."""
    start = time.time()
    while time.time() - start < max_seconds:
        resp = requests.get(f"{BACKEND_URL}/api/v1/verifications/{run_id}")
        assert resp.status_code == 200, f"Failed to poll run: {resp.text}"
        data = resp.json()
        status = data.get("status")
        if status in ("PASSED", "FAILED", "ERROR"):
            return data
        time.sleep(1)
    raise TimeoutError(f"Verification run {run_id} did not finish within {max_seconds} seconds")

def run_scenario_a():
    print_header("SCENARIO A: Multi-File Login Project with Real Defect & Repair")
    zip_path = os.path.join(SCENARIOS_DIR, "demo_scenario_a_login_defective.zip")
    assert os.path.exists(zip_path), f"Scenario A zip not found at {zip_path}"

    # Step 1: Upload ZIP
    print("[1/6] Uploading defective multi-file login project archive...")
    with open(zip_path, "rb") as f:
        files = {"file": ("demo_scenario_a_login_defective.zip", f, "application/zip")}
        resp = requests.post(f"{BACKEND_URL}/api/v1/submissions/upload", files=files)
    assert resp.status_code == 201, f"Upload failed: {resp.text}"
    sub = resp.json()
    submission_id = sub["id"]
    print(f"  ✓ Uploaded submission ID: {submission_id}")
    print(f"  ✓ Detected multi-file: {sub.get('metadata', {}).get('is_multi_file')}")
    print(f"  ✓ Entrypoint: {sub.get('metadata', {}).get('entrypoint')}")
    print(f"  ✓ Total project files: {len(sub.get('metadata', {}).get('project_files', {}))}")

    # Step 2: Create & Execute Verification Run
    print("\n[2/6] Executing Docker sandbox verification...")
    run_resp = requests.post(
        f"{BACKEND_URL}/api/v1/verifications",
        json={"submission_id": submission_id, "triggered_by": "supervisor_demo", "test_types": ["unit"]}
    )
    assert run_resp.status_code == 201, f"Create run failed: {run_resp.text}"
    run_id = run_resp.json()["id"]

    exec_resp = requests.post(f"{BACKEND_URL}/api/v1/verifications/{run_id}/execute")
    assert exec_resp.status_code == 200, f"Execute run failed: {exec_resp.text}"

    run_data = wait_for_run_completion(run_id)
    print(f"  ✓ Initial verification status: {run_data['status']}")
    assert run_data["status"] == "FAILED", f"Expected FAILED status, got {run_data['status']}"

    # Step 3: Inspect Defect Reports & Localization
    defects = run_data.get("defect_reports", [])
    print(f"  ✓ Real defects detected: {len(defects)}")
    for d in defects:
        print(f"    - ID: {d.get('defect_id')}")
        print(f"      Category: {d.get('failure_category')}")
        print(f"      Affected File: {d.get('file_path')}")
        print(f"      Line Number: {d.get('line_number')}")
        print(f"      Failed Test: {d.get('failed_test')}")

    # Step 4: Fetch Technical Feedback Preview & Approve Feedback
    print("\n[3/6] Generating and approving technical feedback for repair...")
    fb_resp = requests.get(f"{BACKEND_URL}/api/v1/verifications/{run_id}/feedback-preview")
    assert fb_resp.status_code == 200, f"Feedback preview failed: {fb_resp.text}"
    feedback = fb_resp.json()
    print(f"  ✓ Feedback summary: {feedback.get('summary', '')[:120]}...")

    # Human-in-the-loop feedback approval gate
    appr_resp = requests.post(
        f"{BACKEND_URL}/api/v1/verifications/{run_id}/approve-feedback",
        json={"approver": "supervisor_demo", "notes": "Approved for repair"}
    )
    assert appr_resp.status_code == 200, f"Feedback approval failed: {appr_resp.text}"
    iteration = appr_resp.json()
    iteration_id = iteration.get("feedback_iteration_id") or iteration.get("id")
    print(f"  ✓ Approved feedback iteration ID: {iteration_id}")

    # Step 5: Ingest Repaired File (auth/service.py)
    print("\n[4/6] Ingesting repaired source file for auth/service.py...")
    repaired_path = os.path.join(SCENARIOS_DIR, "scenario_a_login_service_repaired.py")
    with open(repaired_path, "r", encoding="utf-8") as f:
        repaired_code = f.read()

    repair_payload = {
        "corrected_code": repaired_code,
        "filename": "auth/service.py",
        "repair_source": "LOCAL_MANUAL",
        "feedback_iteration_id": iteration_id,
        "notes": "Fixed password verification on line 28 to call verify_password"
    }
    ingest_resp = requests.post(
        f"{BACKEND_URL}/api/v1/verifications/{run_id}/repair-responses",
        json=repair_payload
    )
    assert ingest_resp.status_code == 201, f"Ingest repair failed: {ingest_resp.text}"
    repair_obj = ingest_resp.json()
    repair_id = repair_obj.get("repair_id") or repair_obj.get("id")
    print(f"  ✓ Ingested repair attempt ID: {repair_id}")

    # Step 6: Re-verify Repaired Submission
    print("\n[5/6] Executing sandboxed re-verification of repaired project...")
    reverify_resp = requests.post(
        f"{BACKEND_URL}/api/v1/verifications/{run_id}/repair-responses/{repair_id}/re-verify",
        json={"force_reverify": False}
    )
    assert reverify_resp.status_code == 200, f"Re-verification failed: {reverify_resp.text}"
    reverify_data = reverify_resp.json()
    print(f"  ✓ Re-verification status: {reverify_data.get('status')}")
    comparison = reverify_data.get("comparison", {})
    print(f"  ✓ Verdict: {comparison.get('verdict')}")
    print(f"  ✓ Original Defects: {comparison.get('original_defects_count')}")
    print(f"  ✓ Resolved Defects: {comparison.get('resolved_defects_count')}")
    print(f"  ✓ Remaining Defects: {comparison.get('remaining_defects_count')}")
    print(f"  ✓ New Defects: {comparison.get('new_defects_count')}")
    assert comparison.get("resolved_defects_count") >= 1, "Expected at least 1 resolved defect"
    assert comparison.get("remaining_defects_count") == 0, "Expected 0 remaining defects"

    # Step 7: Inspect Governance & Convergence
    print("\n[6/6] Verifying convergence and deployment readiness governance...")
    conv_resp = requests.get(f"{BACKEND_URL}/api/v1/verifications/{run_id}/convergence-risk-report")
    assert conv_resp.status_code == 200
    conv_data = conv_resp.json()
    print(f"  ✓ Convergence Risk Level: {conv_data.get('risk_level')}")
    print(f"  ✓ Semantic Drift Score: {conv_data.get('semantic_drift_score')}")

    print("\n>>> Scenario A PASSED successfully with full defect resolution!")
    return {
        "scenario": "A",
        "initial_run_id": run_id,
        "initial_status": run_data["status"],
        "defects_detected": len(defects),
        "repaired_file": "auth/service.py",
        "repair_id": repair_id,
        "reverify_verdict": comparison.get("verdict"),
        "resolved_defects": comparison.get("resolved_defects_count"),
        "remaining_defects": comparison.get("remaining_defects_count"),
    }

def run_scenario_b():
    print_header("SCENARIO B: Defective Project with Blocked Delivery Governance")
    zip_path = os.path.join(SCENARIOS_DIR, "demo_scenario_b_blocked_governance.zip")
    assert os.path.exists(zip_path), f"Scenario B zip not found at {zip_path}"

    print("[1/3] Uploading defective ecommerce calculation project archive...")
    with open(zip_path, "rb") as f:
        files = {"file": ("demo_scenario_b_blocked_governance.zip", f, "application/zip")}
        resp = requests.post(f"{BACKEND_URL}/api/v1/submissions/upload", files=files)
    assert resp.status_code == 201, f"Upload failed: {resp.text}"
    sub = resp.json()
    submission_id = sub["id"]
    print(f"  ✓ Uploaded submission ID: {submission_id}")

    print("\n[2/3] Executing Docker sandbox verification...")
    run_resp = requests.post(
        f"{BACKEND_URL}/api/v1/verifications",
        json={"submission_id": submission_id, "triggered_by": "supervisor_demo", "test_types": ["unit"]}
    )
    assert run_resp.status_code == 201
    run_id = run_resp.json()["id"]

    exec_resp = requests.post(f"{BACKEND_URL}/api/v1/verifications/{run_id}/execute")
    assert exec_resp.status_code == 200

    run_data = wait_for_run_completion(run_id)
    print(f"  ✓ Verification status: {run_data['status']}")
    assert run_data["status"] == "FAILED", f"Expected FAILED status, got {run_data['status']}"

    print("\n[3/3] Inspecting deployment readiness report & testing delivery gate...")
    ready_resp = requests.get(f"{BACKEND_URL}/api/v1/verifications/{run_id}/deployment-readiness-report")
    assert ready_resp.status_code == 200
    ready_data = ready_resp.json()
    print(f"  ✓ Is Ready for Deployment: {ready_data.get('is_ready_for_deployment')}")
    print(f"  ✓ Readiness Status: {ready_data.get('readiness_status')}")
    print(f"  ✓ Blocking Reasons: {ready_data.get('blocking_reasons')}")
    assert ready_data.get("is_ready_for_deployment") is False, "Expected deployment to be BLOCKED"
    assert ready_data.get("readiness_status") == "BLOCKED", "Expected readiness_status == 'BLOCKED'"

    # Attempt delivery confirmation on unverified/failed run - must be rejected
    delivery_attempt = requests.post(
        f"{BACKEND_URL}/api/v1/verifications/{run_id}/delivery-confirmation",
        json={"is_simulation": True, "notes": "Attempting unauthorized delivery on failed code"}
    )
    print(f"  ✓ Delivery attempt response code: {delivery_attempt.status_code}")
    assert delivery_attempt.status_code in (400, 422), f"Expected 400/422 rejection, got {delivery_attempt.status_code}"
    print(f"  ✓ Delivery gate correctly BLOCKED promotion: {delivery_attempt.json().get('error', {}).get('message', delivery_attempt.text)[:120]}")

    print("\n>>> Scenario B PASSED: Delivery safety gate strictly enforced!")
    return {
        "scenario": "B",
        "run_id": run_id,
        "status": run_data["status"],
        "is_ready_for_deployment": ready_data.get("is_ready_for_deployment"),
        "readiness_status": ready_data.get("readiness_status"),
        "delivery_blocked": True,
    }

def run_scenario_c():
    print_header("SCENARIO C: Clean Project Reaching Authorized Post-Delivery XAI")
    zip_path = os.path.join(SCENARIOS_DIR, "demo_scenario_c_clean_delivery_xai.zip")
    assert os.path.exists(zip_path), f"Scenario C zip not found at {zip_path}"

    print("[1/4] Uploading clean statistical analytics project archive...")
    with open(zip_path, "rb") as f:
        files = {"file": ("demo_scenario_c_clean_delivery_xai.zip", f, "application/zip")}
        resp = requests.post(f"{BACKEND_URL}/api/v1/submissions/upload", files=files)
    assert resp.status_code == 201
    sub = resp.json()
    submission_id = sub["id"]
    print(f"  ✓ Uploaded submission ID: {submission_id}")

    print("\n[2/4] Executing Docker sandbox verification...")
    run_resp = requests.post(
        f"{BACKEND_URL}/api/v1/verifications",
        json={"submission_id": submission_id, "triggered_by": "supervisor_demo", "test_types": ["unit"]}
    )
    assert run_resp.status_code == 201
    run_id = run_resp.json()["id"]

    exec_resp = requests.post(f"{BACKEND_URL}/api/v1/verifications/{run_id}/execute")
    assert exec_resp.status_code == 200

    run_data = wait_for_run_completion(run_id)
    print(f"  ✓ Verification status: {run_data['status']}")
    assert run_data["status"] == "PASSED", f"Expected PASSED status, got {run_data['status']}"
    print(f"  ✓ Defects detected: {len(run_data.get('defect_reports', []))}")

    print("\n[3/4] Verifying Post-Delivery XAI gate prior to delivery confirmation...")
    early_expl = requests.get(f"{BACKEND_URL}/api/v1/verifications/{run_id}/explanation").json()
    gate_verdict = early_expl.get('delivery_gate', {}).get('gate_verdict')
    print(f"  ✓ Pre-delivery gate verdict: {gate_verdict}")
    assert gate_verdict == "PENDING_DELIVERY_CONFIRMATION", f"Expected PENDING_DELIVERY_CONFIRMATION, got {gate_verdict}"

    print("\n[4/4] Testing development simulated delivery & production authorization gate...")
    sim_delivery_resp = requests.post(
        f"{BACKEND_URL}/api/v1/verifications/{run_id}/delivery-confirmation",
        json={
            "delivery_channel": "user_workspace",
            "is_simulation": True,
            "notes": "Development-only simulated delivery for supervisor demonstration"
        }
    )
    assert sim_delivery_resp.status_code == 201
    sim_deliv = sim_delivery_resp.json()
    print(f"  ✓ Simulated Delivery ID: {sim_deliv.get('id')} (simulation: {sim_deliv.get('is_simulation')})")

    # Verify that simulated delivery does NOT bypass production post-delivery explanation gate
    early_post_xai = requests.get(f"{BACKEND_URL}/api/v1/verifications/{run_id}/post-delivery-explanation")
    print(f"  ✓ Simulated delivery correctly rejected by production-only gate: {early_post_xai.status_code}")
    assert early_post_xai.status_code in (400, 422)

    # Security check 1: Missing token is rejected
    missing_resp = requests.post(
        f"{BACKEND_URL}/api/v1/verifications/{run_id}/delivery-confirmation",
        json={"delivery_channel": "production_pipeline", "artifact_version": submission_id, "is_simulation": False}
    )
    assert missing_resp.status_code == 400
    print("  ✓ Missing production delivery token correctly rejected (HTTP 400)")

    # Security check 2: Compromised / revoked token is explicitly rejected
    revoked_resp = requests.post(
        f"{BACKEND_URL}/api/v1/verifications/{run_id}/delivery-confirmation",
        headers={"X-Delivery-Token": "intelise_dev_delivery_token_secret"},
        json={"delivery_channel": "production_pipeline", "artifact_version": submission_id, "is_simulation": False}
    )
    assert revoked_resp.status_code == 400
    assert "compromised or revoked" in revoked_resp.text.lower()
    print("  ✓ Compromised / revoked token explicitly rejected (HTTP 400)")

    # Security check 3: Arbitrary invalid token is rejected
    invalid_resp = requests.post(
        f"{BACKEND_URL}/api/v1/verifications/{run_id}/delivery-confirmation",
        headers={"X-Delivery-Token": "invalid_forged_token_attempt_123"},
        json={"delivery_channel": "production_pipeline", "artifact_version": submission_id, "is_simulation": False}
    )
    assert invalid_resp.status_code == 400
    print("  ✓ Arbitrary invalid token rejected (HTTP 400)")

    # Retrieve secure delivery token from environment or local .env
    auth_token = get_delivery_auth_token()
    assert auth_token, "Valid delivery authorization token must be configured in environment or backend/.env"

    # Now confirm production delivery using authorized service token
    prod_delivery_resp = requests.post(
        f"{BACKEND_URL}/api/v1/verifications/{run_id}/delivery-confirmation",
        headers={"X-Delivery-Token": auth_token},
        json={
            "delivery_channel": "production_pipeline",
            "artifact_version": submission_id,
            "is_simulation": False,
            "notes": "Authorized production delivery"
        }
    )
    assert prod_delivery_resp.status_code == 201
    prod_deliv = prod_delivery_resp.json()
    print(f"  ✓ Production Delivery Confirmed ID: {prod_deliv.get('id')} (simulation: {prod_deliv.get('is_simulation')})")

    # Now fetch post-delivery explanation
    xai_resp = requests.get(f"{BACKEND_URL}/api/v1/verifications/{run_id}/post-delivery-explanation")
    assert xai_resp.status_code == 200, f"Post-delivery XAI failed: {xai_resp.text}"
    xai_data = xai_resp.json()
    print(f"  ✓ Post-Delivery XAI package generated successfully!")
    print(f"    - Dimensions present: {len(xai_data.get('dimensions', {}))}")
    print(f"    - Code Summary: {xai_data.get('code_summary', '')[:100]}...")
    print(f"    - Provenance SHA: {xai_data.get('provenance_hash', '')[:16]}...")

    print("\n>>> Scenario C PASSED: Verified code authorized for Post-Delivery XAI!")
    return {
        "scenario": "C",
        "run_id": run_id,
        "status": run_data["status"],
        "delivery_id": prod_deliv.get("id"),
        "delivery_simulation": prod_deliv.get("is_simulation"),
        "xai_generated": True,
        "dimensions_count": len(xai_data.get("dimensions", {})),
    }

def main():
    print_header("INTELISE COMPONENT 4 — SUPERVISOR DEMO AUTOMATED EXECUTION")
    print(f"Backend Target: {BACKEND_URL}")

    # Check health
    try:
        health_resp = requests.get(f"{BACKEND_URL}/health", timeout=5)
        print(f"Backend Health: {health_resp.json()}")
    except Exception as e:
        print(f"ERROR: Backend is not accessible at {BACKEND_URL}: {e}")
        sys.exit(1)

    results = []
    try:
        res_a = run_scenario_a()
        results.append(res_a)

        res_b = run_scenario_b()
        results.append(res_b)

        res_c = run_scenario_c()
        results.append(res_c)

        print_header("DEMONSTRATION EXECUTION SUMMARY")
        for r in results:
            print(f"Scenario {r['scenario']}: SUCCESS -> {r}")

        summary_file = os.path.join(SCENARIOS_DIR, "demo_execution_results.json")
        with open(summary_file, "w", encoding="utf-8") as f:
            json.dump(results, f, indent=2)
        print(f"\nSaved execution summary to {summary_file}")
        print("\nALL 3 DEMO SCENARIOS EXECUTED AND VALIDATED SUCCESSFULLY!")

    except Exception as exc:
        print(f"\nDEMO EXECUTION FAILED: {exc}")
        import traceback
        traceback.print_exc()
        sys.exit(1)

if __name__ == "__main__":
    main()
