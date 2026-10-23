# Verification pipeline incident record — 2026-10-23

This record preserves the observed collection evidence and the post-repair reruns. It does not alter either submitted project.

## Original run evidence

### `run-2e647d7d3aa1`

- Submission: `sub-9c3168e32c58` (`Generated-GPA-Python-Only-For-INTELISE.zip`)
- Original status: `ERROR`
- Classification after investigation: missing sandbox dependency during collection, not a confirmed application defect

```text
ImportError while importing test module '/workspace/test_verification.py'.
Hint: make sure your test modules/packages have valid Python names.
Traceback:
/usr/local/lib/python3.12/importlib/__init__.py:90: in import_module
    return _bootstrap._gcd_import(name[level:], package, level)
           ^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
test_verification.py:1: in <module>
    from fastapi.testclient import TestClient
E   ModuleNotFoundError: No module named 'fastapi'
```

### `run-00f4d8f969e2`

- Submission: `sub-91dd8eb81b2f` (`Generated-GPA-Stdlib-Verification.zip`)
- Original status: `ERROR`
- Classification after investigation: ZIP project-root/PYTHONPATH collection failure, not a confirmed application defect

```text
ImportError while importing test module '/workspace/test_verification.py'.
Hint: make sure your test modules/packages have valid Python names.
Traceback:
/usr/local/lib/python3.12/importlib/__init__.py:90: in import_module
    return _bootstrap._gcd_import(name[level:], package, level)
           ^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
test_verification.py:2: in <module>
    from app.gpa import validate_request, compute_gpa, GpaError, InMemoryRepository
E   ModuleNotFoundError: No module named 'app'
```

The second archive stored `app/gpa.py` below the wrapper directory `Generated-GPA-Stdlib-Verification/`. The old runner mounted the extraction directory at `/workspace`, copied the primary test to `/workspace/test_verification.py`, and exported only `PYTHONPATH=/workspace`. Therefore `app` was actually at `/workspace/Generated-GPA-Stdlib-Verification/app` and could not be imported.

## Unchanged-submission reruns

The service does not retain original ZIP binary bytes; it retains the validated extracted file map. The reruns referenced the same persisted submission IDs and did not update their contents. Canonical SHA-256 hashes of the sorted extracted file maps were:

- `sub-9c3168e32c58`: `d8ed0f83b9b998e0c667c290703046a61b9e17b95f1a41e999587b625bd8d1fa`
- `sub-91dd8eb81b2f`: `94b61f5c56f733e02b7061bdc37a61e96c2fc5997014a9209f9ae9fd54546e3d`

Results in the network-disabled, non-root, read-only Docker sandbox:

- `run-b842d796fc7d` (FastAPI): 3 genuine embedded tests passed; unit `PASSED`, integration `NOT_EXECUTED`, performance `NOT_EXECUTED`, overall `BLOCKED`, 0 defect reports.
- `run-d99192f3568b` (standard library): 7 genuine embedded tests passed; unit `PASSED`, integration `NOT_EXECUTED`, performance `NOT_EXECUTED`, overall `BLOCKED`, 0 defect reports.

The overall outcomes remain `BLOCKED` because the original requests included integration and performance, but neither archive supplied authorized workloads for those categories. No performance measurements or pass verdicts are claimed.
