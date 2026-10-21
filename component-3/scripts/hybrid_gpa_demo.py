"""Reproducible GPA benchmark for the hybrid pipeline (PP1: LOCAL_SANDBOX_PREVIEW).

Runs the acceptance scenario against SIMULATED C1/C2/C4 fixtures and prints the
evidence. Steps that need Docker run only with --preview. Nothing is deployed and
no external service or repository is modified (OpenRouter is not called unless
--with-llm is given and the backend is configured for it).

    .venv\\Scripts\\python.exe scripts\\hybrid_gpa_demo.py --isolated
    .venv\\Scripts\\python.exe scripts\\hybrid_gpa_demo.py --preview          # leaves the preview running
    .venv\\Scripts\\python.exe scripts\\hybrid_gpa_demo.py --preview --stop   # stops it at the end
"""

from __future__ import annotations

import argparse
import asyncio
from collections import Counter
from datetime import UTC, datetime
import json
import shutil
import sys
from uuid import uuid4

from intelise_c3.contracts.hybrid import (
    C4DefectSubmission,
    DeploymentGateRequest,
    HybridGenerationRequest,
    RequirementChangeRequest,
)
from intelise_c3.core.config import COMPONENT_ROOT, Settings
from intelise_c3.core.errors import ApplicationError
from intelise_c3.hybrid.pipeline import HybridPipeline

FIXTURES = COMPONENT_ROOT / "tests" / "fixtures" / "hybrid"


def _load(name: str) -> dict:
    return json.loads((FIXTURES / name).read_text(encoding="utf-8"))


async def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--isolated", action="store_true", help="use a throwaway workspace and trace store under tmp/")
    parser.add_argument("--preview", action="store_true", help="build and start the Docker LOCAL_SANDBOX_PREVIEW")
    parser.add_argument("--stop", action="store_true", help="stop the preview at the end (default: leave it running)")
    args = parser.parse_args()

    if args.isolated:
        work = COMPONENT_ROOT / "tmp" / f"hybrid-demo-{uuid4().hex[:8]}"
        settings = Settings(generated_workspace_root=work / "ws", traceability_store_path=work / "trace.sqlite3",
                            hybrid_llm_cache_dir=work / "cache")
    else:
        work, settings = None, Settings()
    pipeline = HybridPipeline(settings)
    template = pipeline.policy_acceptance_template()
    acceptance = {"policy_id": template["policy_id"], "policy_version": template["policy_version"],
                  "policy_digest_sha256": template["policy_digest_sha256"], "accepted_by": "pp1-demo-researcher",
                  "acceptance_reference": "PP1-DEMO-ACCEPT-001", "acknowledges_sample_status": True}
    evidence: dict = {"started_at_utc": datetime.now(UTC).isoformat(), "isolated": args.isolated}

    def step(number: int, title: str, value) -> None:
        evidence[f"{number:02d} {title}"] = value
        print(f"[{number:02d}] {title}: {value if not isinstance(value, (dict, list)) else json.dumps(value)[:300]}")

    package = _load("gpa_input_package.json")
    step(1, "C1 fixture", f"{package['c1']['project_id']} {package['c1']['srs_version']} {package['c1']['approval_status']} ({package['c1']['evidence_class']})")
    step(2, "C2 fixture", f"{package['c2']['uml_version']} {package['c2']['release_status']} for {package['c2']['srs_version']} ({package['c2']['evidence_class']})")
    step(3, "Requirement-to-UML anchors", len(package["c2"]["requirement_uml_anchors"]))
    step(4, "Policy", f"{template['policy_id']} v{template['policy_version']} {template['authority_status']} accepted explicitly")
    request = HybridGenerationRequest.model_validate({"package": package, "policy_acceptance": acceptance, "workspace_name": "gpa-benchmark"})
    first = await pipeline.generate(request)
    second = await pipeline.generate(request)
    m = second["manifest"]
    step(5, "Stack", f"{m['stack']['stack_id']} ({m['stack']['criteria_source']}): {m['stack']['reason']}")
    step(6, "Rules selected", m["rule_set"]["selected_rules"])
    step(7, "Deterministic modules", f"{len(m['llm']['deterministic_modules'])} template modules, {len(m['files'])} files")
    step(8, "RAG chunks (guidance only)", sum(len(r["hits"]) for r in m["rag"]["retrievals"]))
    step(9, "OpenRouter calls / tokens", f"{m['llm']['calls']} calls, {m['llm']['prompt_tokens'] + m['llm']['completion_tokens']} tokens")
    step(10, "Artifact folders", sorted({f['path'].split('/')[0] for f in m['files']}))
    coverage = m["traceability"]["coverage"]
    step(11, "Traceability", f"{coverage['traced_count']}/{coverage['total']} requirements traced; orphans {len(coverage['orphan_artifacts'])}")
    step(12, "Verification", m["verification"])
    step(13, "Determinism (two runs)", {"identical_artifact_digest": first["manifest"]["artifact_digest_sha256"] == m["artifact_digest_sha256"],
                                        "digest": m["artifact_digest_sha256"]})
    preview_id = None
    if args.preview:
        from intelise_c3.hybrid.preview import HybridPreviewService

        service = HybridPreviewService(pipeline)
        session = service.start(second["generation_run_id"])
        preview_id = session["preview_id"]
        step(14, "Docker preview", {k: session.get(k) for k in ("status", "frontend_url", "api_url", "container_name", "health")})
        step(15, "Known GPA calculation", service.gpa_check(preview_id))
    else:
        step(14, "Docker preview", "skipped (use --preview)")
    change = await pipeline.requirement_change(RequirementChangeRequest.model_validate({
        "base_generation_run_id": second["generation_run_id"], "package": _load("gpa_input_package_req103_v2.json"),
        "policy_acceptance": acceptance}))
    lineage = change["manifest"]["lineage"]
    step(16, "Changed requirement", lineage["changed_requirement_ids"])
    step(17, "Impact set", lineage["impact_set"])
    step(18, "Scoped regeneration hash preservation", dict(Counter(r["state"] for r in lineage["preservation"])))
    step(19, "Trace link changes", change["link_changes"])
    injected = pipeline.inject_defect_for_demo(change["generation_run_id"])
    submission = pipeline.simulated_defect(injected["generation_run_id"])["submission"]
    repaired = await pipeline.c4_defect(C4DefectSubmission.model_validate(submission))
    step(20, "Injected defect -> SIMULATED C4 report -> scoped repair",
         {"impact": repaired["manifest"]["lineage"]["impact_set"],
          "restored_digest_equals_pre_defect": repaired["manifest"]["artifact_digest_sha256"] == change["manifest"]["artifact_digest_sha256"]})
    try:
        await pipeline.c4_defect(C4DefectSubmission.model_validate(submission))
        stale = "NOT_REJECTED"
    except ApplicationError as error:
        stale = error.errors[0].code
    step(21, "Stale C4 report rejected", stale)
    run_id = repaired["generation_run_id"]
    blocked = pipeline.deployment_gate(DeploymentGateRequest(generation_run_id=run_id))
    step(22, "Gate stub without readiness", {"decision": blocked["decision"], "reasons": blocked["reasons"]})
    old_signal = pipeline.simulated_readiness(change["generation_run_id"])["readiness_signal"]
    mismatched = pipeline.deployment_gate(DeploymentGateRequest.model_validate({"generation_run_id": run_id, "readiness_signal": old_signal}))
    step(23, "Gate stub with readiness for a different artifact", {"decision": mismatched["decision"], "reasons": mismatched["reasons"]})
    signal = pipeline.simulated_readiness(run_id)["readiness_signal"]
    allowed = pipeline.deployment_gate(DeploymentGateRequest.model_validate({"generation_run_id": run_id, "readiness_signal": signal}))
    step(24, "Gate stub with exact SIMULATED readiness", {"decision": allowed["decision"], "scope": allowed["authorization_scope"],
                                                          "action": allowed["deployment_action"]})
    audit = pipeline.audit_markdown(run_id)
    out = COMPONENT_ROOT / "runtime" / "hybrid-demo" / datetime.now(UTC).strftime("%Y%m%dt%H%M%Sz")
    out.mkdir(parents=True, exist_ok=True)
    (out / "evidence.json").write_text(json.dumps(evidence, indent=2, default=str), encoding="utf-8")
    (out / "audit.md").write_text(audit, encoding="utf-8")
    step(25, "Audit report", str(out.relative_to(COMPONENT_ROOT)))
    if preview_id and args.stop:
        stopped = service.stop(preview_id)
        print(f"Preview {preview_id} stopped; removed {stopped['removed_containers']}")
    elif preview_id:
        print(f"Preview {preview_id} left running. Stop it from the dashboard or with: "
              f"docker rm -f {preview_id}-web {preview_id}-api {preview_id}-db && "
              f"docker network rm {preview_id}-edge {preview_id}-dbnet")
    if work is not None:
        shutil.rmtree(work, ignore_errors=True)
    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
