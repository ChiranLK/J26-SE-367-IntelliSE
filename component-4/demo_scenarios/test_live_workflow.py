import asyncio
import json
import httpx

BASE_URL = "http://127.0.0.1:8000/api/v1"

async def test_live_scenarios():
    async with httpx.AsyncClient(timeout=120.0) as client:
        print("=== 1. Health & Engine Status ===")
        health = (await client.get(f"{BASE_URL}/health")).json()
        print(f"Health: status={health['status']}, storage={health['storage_backend']}")
        
        ai_engine = (await client.get(f"{BASE_URL}/verifications/status/ai-engine")).json()
        print(f"AI Engine: connected={ai_engine['ollama_connected']}, model={ai_engine['configured_model']}")

        # ------------------------------------------------------------------
        # SCENARIO A: Defective Project
        # ------------------------------------------------------------------
        print("\n=== 2. Scenario A: Defective Project (friday_defective_three_tests.zip) ===")
        with open("demo_scenarios/friday_defective_three_tests.zip", "rb") as f:
            zip_bytes = f.read()

        upload_resp = await client.post(
            f"{BASE_URL}/submissions/upload",
            files={"file": ("friday_defective_three_tests.zip", zip_bytes, "application/zip")},
            data={"requirement_ids": "REQ-SHOP-01,REQ-SHOP-02"}
        )
        assert upload_resp.status_code == 201, upload_resp.text
        sub_defective = upload_resp.json()
        print(f"Uploaded defective submission: id={sub_defective['id']}")

        create_resp = await client.post(
            f"{BASE_URL}/verifications",
            json={
                "submission_id": sub_defective["id"],
                "triggered_by": "live_demo_test",
                "test_types": ["unit", "integration", "performance"],
            }
        )
        assert create_resp.status_code == 201, create_resp.text
        run_defective = create_resp.json()
        print(f"Created verification run: id={run_defective['id']}")

        print("Executing in Docker container...")
        exec_resp = await client.post(f"{BASE_URL}/verifications/{run_defective['id']}/execute", json={})
        assert exec_resp.status_code == 200, exec_resp.text
        executed_defective = exec_resp.json()

        print(f"Defective Run Overall Status: {executed_defective['status']}")
        agent_reports = executed_defective.get("execution_telemetry", {}).get("agent_reports", {})
        for cat in ("unit", "integration", "performance"):
            rep = agent_reports.get(cat, {})
            print(f"  - {cat.upper()}: status={rep.get('status')}, passed={rep.get('passed_tests') or rep.get('passed_interactions')}, failed={rep.get('failed_tests') or rep.get('failed_interactions')}")

        print(f"Defect reports count: {len(executed_defective.get('defect_reports', []))}")
        for d in executed_defective.get("defect_reports", []):
            print(f"  - Defect: {d.get('title')} at {d.get('file_path')}:{d.get('line_number')}")

        # Check Post-Delivery XAI gate for defective run
        xai_resp = await client.get(f"{BASE_URL}/verifications/{run_defective['id']}/explanation")
        assert xai_resp.status_code == 200
        xai_defective = xai_resp.json()
        print(f"XAI Gate Verdict: {xai_defective.get('delivery_status')} (eligible={xai_defective.get('eligible')})")
        print(f"Post-delivery XAI available: {xai_defective.get('post_delivery_explanation') is not None}")

        # Try to confirm delivery on defective run (must fail closed)
        deliv_attempt = await client.post(f"{BASE_URL}/verifications/{run_defective['id']}/delivery-confirmation", json={"is_simulation": True})
        print(f"Attempt delivery on failed run: status_code={deliv_attempt.status_code} (expected 400)")

        # ------------------------------------------------------------------
        # SCENARIO B: Clean Project
        # ------------------------------------------------------------------
        print("\n=== 3. Scenario B: Clean Project (friday_clean_three_tests.zip) ===")
        with open("demo_scenarios/friday_clean_three_tests.zip", "rb") as f:
            clean_zip_bytes = f.read()

        upload_clean_resp = await client.post(
            f"{BASE_URL}/submissions/upload",
            files={"file": ("friday_clean_three_tests.zip", clean_zip_bytes, "application/zip")},
            data={"requirement_ids": "REQ-SHOP-01,REQ-SHOP-02"}
        )
        assert upload_clean_resp.status_code == 201, upload_clean_resp.text
        sub_clean = upload_clean_resp.json()
        print(f"Uploaded clean submission: id={sub_clean['id']}")

        create_clean_resp = await client.post(
            f"{BASE_URL}/verifications",
            json={
                "submission_id": sub_clean["id"],
                "triggered_by": "live_demo_test",
                "test_types": ["unit", "integration", "performance"],
            }
        )
        assert create_clean_resp.status_code == 201, create_clean_resp.text
        run_clean = create_clean_resp.json()
        print(f"Created verification run: id={run_clean['id']}")

        print("Executing clean project in Docker container...")
        exec_clean_resp = await client.post(f"{BASE_URL}/verifications/{run_clean['id']}/execute", json={})
        assert exec_clean_resp.status_code == 200, exec_clean_resp.text
        executed_clean = exec_clean_resp.json()

        print(f"Clean Run Overall Status: {executed_clean['status']}")
        clean_reports = executed_clean.get("execution_telemetry", {}).get("agent_reports", {})
        for cat in ("unit", "integration", "performance"):
            rep = clean_reports.get(cat, {})
            print(f"  - {cat.upper()}: status={rep.get('status')}, passed={rep.get('passed_tests') or rep.get('passed_interactions')}, failed={rep.get('failed_tests') or rep.get('failed_interactions')}")

        # Check XAI before delivery confirmation
        xai_clean_pre = (await client.get(f"{BASE_URL}/verifications/{run_clean['id']}/explanation")).json()
        print(f"XAI Gate before delivery: {xai_clean_pre.get('delivery_status')}")
        print(f"Post-delivery explanation present before delivery: {xai_clean_pre.get('post_delivery_explanation') is not None}")

        # Confirm simulated delivery
        print("Authorizing development delivery simulation...")
        deliv_clean = (await client.post(
            f"{BASE_URL}/verifications/{run_clean['id']}/delivery-confirmation",
            json={"is_simulation": True, "notes": "Live validation test for Friday supervisor demo"}
        )).json()
        print(f"Delivery Confirmed: id={deliv_clean.get('delivery_id')}, channel={deliv_clean.get('delivery_channel')}, is_simulation={deliv_clean.get('is_simulation')}")

        # Fetch Post-Delivery XAI with Ollama
        print("Generating human-facing Post-Delivery XAI with Ollama qwen2.5-coder:3b...")
        xai_clean_post = (await client.get(f"{BASE_URL}/verifications/{run_clean['id']}/explanation")).json()
        print(f"XAI Gate after delivery: {xai_clean_post.get('delivery_status')}")
        pdx = xai_clean_post.get("post_delivery_explanation")
        print(f"Post-delivery explanation present: {pdx is not None}")
        if pdx:
            print(f"  - Software Title: {pdx.get('software_name')}")
            print(f"  - Software Overview: {pdx.get('software_overview')[:100]}...")
            print(f"  - Architecture: {pdx.get('architecture_explanation')[:100]}...")
            print(f"  - Module Responsibilities count: {len(pdx.get('module_responsibilities') or [])}")
            print(f"  - Important Functions count: {len(pdx.get('important_functions') or [])}")
        prov = xai_clean_post.get("inference_provenance", {})
        print(f"Inference Provenance: model={prov.get('model')}, genuine_inference={prov.get('genuine_inference')}, duration_ms={prov.get('duration_ms')}")

        # ------------------------------------------------------------------
        # SCENARIO C: Unsupported C submission
        # ------------------------------------------------------------------
        print("\n=== 4. Scenario C: Unsupported C Code ===")
        sub_c = (await client.post(
            f"{BASE_URL}/submissions",
            json={
                "code": "#include <stdio.h>\nint main() { printf(\"Hello\"); return 0; }\n",
                "language": "c",
                "filename": "main.c",
            }
        )).json()
        print(f"Submitted C code: id={sub_c['id']}")

        run_c = (await client.post(
            f"{BASE_URL}/verifications",
            json={"submission_id": sub_c["id"], "triggered_by": "c_test"}
        )).json()
        print(f"Created run for C code: id={run_c['id']}")

        exec_c = (await client.post(f"{BASE_URL}/verifications/{run_c['id']}/execute", json={})).json()
        print(f"Executed C run: status={exec_c['status']}, error_message={exec_c['error_message']}")

        print("\n=== ALL LIVE SCENARIOS COMPLETED SUCCESSFULLY ===")

if __name__ == "__main__":
    asyncio.run(test_live_scenarios())
