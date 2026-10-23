import io
import uuid
import zipfile
from datetime import datetime, timezone
import pytest
from starlette.testclient import TestClient

from app.core.errors import FileValidationException
from app.repositories import (
    _in_memory_repair_repo,
    _in_memory_submission_repo,
    _in_memory_test_suite_repo,
    _in_memory_verification_repo,
)
from app.schemas.common import (
    DefectSeverity,
    ProgrammingLanguage,
    SubmissionSource,
    TestResultStatus,
    TestType,
    VerificationStatus,
)
from app.schemas.defect_report import DefectReport
from app.schemas.feedback import FeedbackIteration
from app.schemas.repair import RepairResponseIngestRequest, RepairSource
from app.schemas.submission import CodeSubmissionResponse
from app.schemas.test_result import TestResult
from app.schemas.verification import VerificationRunResponse
from app.services.defect_analysis_service import DefectAnalysisService
from app.services.repair_service import RepairService
from app.services.verification_service import VerificationService


def create_zip_bytes(file_dict: dict) -> bytes:
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w", zipfile.ZIP_DEFLATED) as zf:
        for filename, content in file_dict.items():
            zf.writestr(filename, content)
    buffer.seek(0)
    return buffer.getvalue()


# ==========================================
# 1. ZIP Upload and Validation Security Tests (via FastAPI client)
# ==========================================

def test_valid_project_zip_upload(client: TestClient):
    files_map = {
        "auth/__init__.py": "",
        "auth/login.py": "def authenticate(u, p):\n    return u == 'admin' and p == 'secret123'\n",
        "tests/__init__.py": "",
        "tests/test_login.py": "from auth.login import authenticate\ndef test_auth():\n    assert authenticate('admin', 'secret123') is True\n",
        "README.md": "# Login Service\n",
    }
    zip_bytes = create_zip_bytes(files_map)
    files = {"file": ("login_project.zip", io.BytesIO(zip_bytes), "application/zip")}
    data = {"requirement_ids": "REQ-AUTH-01"}

    response = client.post("/api/v1/submissions/upload", files=files, data=data)
    assert response.status_code == 201
    res = response.json()

    assert res["id"].startswith("sub-")
    assert res["filename"] == "login_project.zip"
    meta = res.get("metadata", {})
    assert meta.get("is_multi_file") is True
    assert meta.get("file_count") == 5
    assert "auth/login.py" in meta["project_files"]
    assert "tests/test_login.py" in meta["project_files"]
    assert "authenticate" in res["code"]


def test_zip_path_traversal_rejected(client: TestClient):
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w") as zf:
        zf.writestr("../evil.py", "import os; os.system('echo hacked')")
    buffer.seek(0)
    files = {"file": ("exploit.zip", io.BytesIO(buffer.getvalue()), "application/zip")}

    response = client.post("/api/v1/submissions/upload", files=files)
    assert response.status_code == 400
    assert "traversal" in response.json()["error"]["message"].lower()


def test_zip_absolute_path_rejected(client: TestClient):
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w") as zf:
        zf.writestr("/etc/evil.py", "malicious_code = True")
    buffer.seek(0)
    files = {"file": ("abs.zip", io.BytesIO(buffer.getvalue()), "application/zip")}

    response = client.post("/api/v1/submissions/upload", files=files)
    assert response.status_code == 400
    msg = response.json()["error"]["message"].lower()
    assert "traversal" in msg or "absolute" in msg


def test_zip_dangerous_file_rejected(client: TestClient):
    files_map = {
        "main.py": "print('hello')",
        "payload.exe": "MZ\x90\x00BinaryExeContentHere",
    }
    zip_bytes = create_zip_bytes(files_map)
    files = {"file": ("payload.zip", io.BytesIO(zip_bytes), "application/zip")}

    response = client.post("/api/v1/submissions/upload", files=files)
    assert response.status_code == 400
    msg = response.json()["error"]["message"].lower()
    assert "unsafe executable" in msg or "prohibited" in msg


def test_zip_too_many_files_rejected(client: TestClient):
    files_map = {f"file_{i}.py": f"# File {i}" for i in range(105)}
    zip_bytes = create_zip_bytes(files_map)
    files = {"file": ("large.zip", io.BytesIO(zip_bytes), "application/zip")}

    response = client.post("/api/v1/submissions/upload", files=files)
    assert response.status_code == 400
    msg = response.json()["error"]["message"].lower()
    assert "maximum allowed file count" in msg and "105 entries" in msg


def test_zip_bomb_compression_ratio_rejected(client: TestClient):
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w", zipfile.ZIP_DEFLATED) as zf:
        zf.writestr("zeroes.txt", "0" * (1024 * 1024))
    buffer.seek(0)
    files = {"file": ("bomb.zip", io.BytesIO(buffer.getvalue()), "application/zip")}

    response = client.post("/api/v1/submissions/upload", files=files)
    assert response.status_code == 400
    assert "compression ratio" in response.json()["error"]["message"].lower()


# ==========================================
# 2. Multi-File Defect Localization Tests
# ==========================================

def test_multi_file_traceback_localization():
    service = DefectAnalysisService()
    project_files = {
        "auth/__init__.py": "",
        "auth/login.py": "def authenticate(u):\n    return u['role'] == 'admin'\n",
        "models/user.py": "class User:\n    pass\n",
        "tests/test_login.py": "from auth.login import authenticate\ndef test():\n    authenticate({'name': 'alice'})\n",
    }
    stack_trace = """
Traceback (most recent call last):
  File "/workspace/tests/test_login.py", line 3, in test
    authenticate({'name': 'alice'})
  File "/workspace/auth/login.py", line 2, in authenticate
    return u['role'] == 'admin'
KeyError: 'role'
"""
    rel_path, line_no, conf, prov = service.extract_multi_file_traceback_localization(
        stack_trace=stack_trace,
        project_files=project_files,
        default_filename="solution.py",
    )

    assert rel_path == "auth/login.py"
    assert line_no == 2
    assert conf == "CONFIRMED"
    assert prov == "TRACEBACK_FRAME_ANALYSIS"


def test_multi_file_static_security_scan():
    service = DefectAnalysisService()
    project_files = {
        "auth/login.py": "def login():\n    return True\n",
        "auth/hasher.py": "import os\ndef execute_command(cmd):\n    os.system(cmd)\n",
        "tests/test_login.py": "def test(): pass\n",
    }
    reports = service.analyze_test_results(
        run_id="run-test-sec",
        submission_id="sub-test-sec",
        status="PASSED",
        test_results=[],
        project_files=project_files,
    )

    sec_reports = [r for r in reports if r.cwe_id == "CWE-78"]
    assert len(sec_reports) == 1
    assert sec_reports[0].file_path == "auth/hasher.py"
    assert sec_reports[0].line_number == 3
    assert sec_reports[0].confidence == "CONFIRMED"


def test_collection_failure_is_not_reported_as_confirmed_source_defect():
    service = DefectAnalysisService()
    result = TestResult(
        test_id="collection-app",
        name="test_verification",
        test_type=TestType.UNIT,
        status=TestResultStatus.ERROR,
        error_message="collection failure",
        stack_trace="ModuleNotFoundError: No module named 'app'",
        metrics={"failure_origin": "COLLECTION_ERROR", "pytest_exit_code": 2},
    )

    reports = service.analyze_test_results(
        run_id="run-collection",
        submission_id="sub-collection",
        status="ERROR",
        test_results=[result],
        project_files={
            "wrapper/app/__init__.py": "",
            "wrapper/app/gpa.py": "def compute(): return 4.0\n",
            "wrapper/tests/test_gpa.py": "from app.gpa import compute\n",
        },
    )

    assert reports == []


# ==========================================
# 3. Multi-File Repair Ingestion Tests
# ==========================================

def test_multi_file_repair_ingestion_patches_project_files():
    import asyncio
    ver_service = VerificationService(
        _in_memory_submission_repo,
        _in_memory_verification_repo,
        _in_memory_test_suite_repo,
    )
    repair_service = RepairService(
        _in_memory_repair_repo,
        _in_memory_submission_repo,
        _in_memory_verification_repo,
        ver_service,
        test_suite_repo=_in_memory_test_suite_repo,
    )

    async def _test():
        now = datetime.now(timezone.utc)
        sub_id = f"sub-{uuid.uuid4().hex[:12]}"
        project_files = {
            "auth/__init__.py": "",
            "auth/login.py": "def authenticate(user):\n    return user['role'] == 'admin'\n",
            "models/user.py": "class User:\n    pass\n",
        }
        sub = CodeSubmissionResponse(
            id=sub_id,
            code=project_files["auth/login.py"],
            language=ProgrammingLanguage.PYTHON,
            filename="auth/login.py",
            requirement_ids=["REQ-01"],
            source_type=SubmissionSource.FILE_UPLOAD,
            test_code="def test_fake(): assert False\n",
            created_at=now,
            metadata={
                "is_multi_file": True,
                "project_files": dict(project_files),
                "entrypoint": "auth/login.py",
            },
        )
        await _in_memory_submission_repo.save(sub)

        # Failed run
        run_id = f"run-{uuid.uuid4().hex[:12]}"
        iteration = FeedbackIteration(
            iteration_id="iter-001",
            iteration_number=1,
            verification_run_id=run_id,
            submission_id=sub.id,
            correlation_id="corr-1",
            approval_status="APPROVED",
        )
        run_resp = VerificationRunResponse(
            id=run_id,
            submission_id=sub.id,
            status=VerificationStatus.FAILED,
            test_results=[
                TestResult(
                    test_id="t1",
                    name="test_login",
                    test_type=TestType.UNIT,
                    status=TestResultStatus.FAILED,
                    duration_ms=10.0,
                )
            ],
            defect_reports=[
                DefectReport(
                    defect_id="def-1",
                    verification_run_id=run_id,
                    submission_id=sub.id,
                    title="KeyError",
                    description="KeyError: role",
                    failed_test="test_login",
                    severity=DefectSeverity.HIGH,
                    created_at=now,
                )
            ],
            feedback_iterations=[iteration],
            created_at=now,
            updated_at=now,
        )
        await _in_memory_verification_repo.save(run_resp)

        # Ingest repair for auth/login.py
        fixed_code = "def authenticate(user):\n    return user.get('role') == 'admin'\n"
        attempt = await repair_service.ingest_repair_response(
            original_run_id=run_id,
            request=RepairResponseIngestRequest(
                corrected_code=fixed_code,
                filename="auth/login.py",
                feedback_iteration_id="iter-001",
                repair_source=RepairSource.LOCAL_MANUAL,
            ),
        )

        assert attempt.id.startswith("rep-")
        new_sub = await _in_memory_submission_repo.get_by_id(attempt.corrected_submission_id)
        assert new_sub is not None
        assert new_sub.metadata["is_multi_file"] is True
        assert new_sub.metadata["repaired_file"] == "auth/login.py"
        # Verify auth/login.py was updated in project_files
        assert new_sub.metadata["project_files"]["auth/login.py"] == fixed_code
        # Verify models/user.py was preserved untouched
        assert new_sub.metadata["project_files"]["models/user.py"] == project_files["models/user.py"]

    asyncio.run(_test())
