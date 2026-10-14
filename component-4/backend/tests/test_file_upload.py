import io
from starlette.testclient import TestClient
from app.core.config import settings


def test_upload_valid_python_file(client: TestClient):
    """Verify safe upload of a valid Python file with automatic language detection."""
    file_content = b"def greet(name: str) -> str:\n    return f'Hello {name}'\n"
    files = {"file": ("greeter.py", io.BytesIO(file_content), "text/x-python")}
    data = {"requirement_ids": "REQ-101, REQ-102"}

    response = client.post("/api/v1/submissions/upload", files=files, data=data)
    assert response.status_code == 201
    res_data = response.json()

    assert res_data["id"].startswith("sub-")
    assert res_data["filename"] == "greeter.py"
    assert res_data["language"] == "python"
    assert "def greet(name: str)" in res_data["code"]
    assert res_data["requirement_ids"] == ["REQ-101", "REQ-102"]
    assert res_data["source_type"] == "file_upload"
    assert res_data["metadata"]["file_size_bytes"] == len(file_content)


def test_upload_with_language_override(client: TestClient):
    """Verify that specifying explicit language in upload overrides extension detection."""
    file_content = b"const x: number = 42;\n"
    files = {"file": ("snippet.txt", io.BytesIO(file_content), "text/plain")}
    data = {"language": "typescript"}

    response = client.post("/api/v1/submissions/upload", files=files, data=data)
    assert response.status_code == 201
    res_data = response.json()
    assert res_data["language"] == "typescript"
    assert res_data["filename"] == "snippet.txt"


def test_upload_path_traversal_sanitization(client: TestClient):
    """Verify that dangerous directory traversal paths in uploaded filenames are sanitized."""
    file_content = b"print('safe')"
    files = {
        "file": (
            "../../etc/passwd/script.py",
            io.BytesIO(file_content),
            "text/x-python",
        )
    }

    response = client.post("/api/v1/submissions/upload", files=files)
    assert response.status_code == 201
    res_data = response.json()
    assert res_data["filename"] == "script.py"
    assert "/" not in res_data["filename"]
    assert ".." not in res_data["filename"]


def test_upload_disallowed_extension_rejected(client: TestClient):
    """Verify that file extensions not on the allowlist (e.g. .exe) are rejected with 400."""
    file_content = b"MZ\x90\x00\x03\x00\x00\x00"
    files = {"file": ("malware.exe", io.BytesIO(file_content), "application/octet-stream")}

    response = client.post("/api/v1/submissions/upload", files=files)
    assert response.status_code == 400
    res_data = response.json()
    assert res_data["error"]["code"] == "FILE_VALIDATION_ERROR"
    assert "is not permitted" in res_data["error"]["message"]


def test_upload_empty_file_rejected(client: TestClient):
    """Verify that an empty file upload is rejected with 400."""
    files = {"file": ("empty.py", io.BytesIO(b""), "text/x-python")}

    response = client.post("/api/v1/submissions/upload", files=files)
    assert response.status_code == 400
    res_data = response.json()
    assert res_data["error"]["code"] == "FILE_VALIDATION_ERROR"
    assert "empty" in res_data["error"]["message"].lower()


def test_upload_oversized_file_rejected(client: TestClient):
    """Verify that files exceeding MAX_UPLOAD_SIZE_BYTES are rejected with 413."""
    oversized_bytes = b"a" * (settings.MAX_UPLOAD_SIZE_BYTES + 1024)
    files = {"file": ("large_file.py", io.BytesIO(oversized_bytes), "text/x-python")}

    response = client.post("/api/v1/submissions/upload", files=files)
    assert response.status_code == 413
    res_data = response.json()
    assert res_data["error"]["code"] == "FILE_VALIDATION_ERROR"
    assert "exceeds the allowed limit" in res_data["error"]["message"]


def test_upload_binary_non_utf8_rejected(client: TestClient):
    """Verify that non-UTF-8 binary files are rejected with 400."""
    # Invalid UTF-8 sequence
    invalid_utf8_bytes = b"\xff\xfe\x00\x00\x80\x81\x82\x83"
    files = {"file": ("corrupt.py", io.BytesIO(invalid_utf8_bytes), "text/x-python")}

    response = client.post("/api/v1/submissions/upload", files=files)
    assert response.status_code == 400
    res_data = response.json()
    assert res_data["error"]["code"] == "FILE_VALIDATION_ERROR"
    assert "UTF-8" in res_data["error"]["message"]


def test_upload_null_byte_in_filename_rejected(client: TestClient):
    """Verify that filenames containing null bytes are rejected with 400."""
    files = {"file": ("test\x00malicious.py", io.BytesIO(b"print('x')"), "text/x-python")}
    response = client.post("/api/v1/submissions/upload", files=files)
    assert response.status_code == 400
    res_data = response.json()
    assert res_data["error"]["code"] == "FILE_VALIDATION_ERROR"
    assert "null" in res_data["error"]["message"].lower()


def test_upload_missing_extension_rejected(client: TestClient):
    """Verify that uploaded files without an extension are rejected with 400."""
    files = {"file": ("noextension", io.BytesIO(b"print('x')"), "text/plain")}
    response = client.post("/api/v1/submissions/upload", files=files)
    assert response.status_code == 400
    res_data = response.json()
    assert res_data["error"]["code"] == "FILE_VALIDATION_ERROR"
    assert "extension" in res_data["error"]["message"].lower()


def test_upload_windows_style_path_sanitized(client: TestClient):
    """Verify that Windows-style backslashes in uploaded filenames are safely stripped."""
    files = {"file": ("C:\\Users\\Developer\\Documents\\script.py", io.BytesIO(b"print('safe')"), "text/x-python")}
    response = client.post("/api/v1/submissions/upload", files=files)
    assert response.status_code == 201
    res_data = response.json()
    assert res_data["filename"] == "script.py"
    assert "\\" not in res_data["filename"]
    assert "/" not in res_data["filename"]

