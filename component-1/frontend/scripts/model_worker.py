"""Local dev-only inference bridge. Reuse the backend's trusted artifact loader.

One process, lazy model loading, JSON-lines over pipes; no HTTP, DB or training.
Never print input text, traceback details or model paths to diagnostics.
"""
import json
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

classifier = None
for line in sys.stdin:
    try:
        request = json.loads(line)
        text = request["requirement_text"]
        if not isinstance(text, str) or not text.strip() or len(text) > 5000:
            raise ValueError()
        started = time.monotonic()
        if classifier is None:
            from intelise_c1.services.classifier import LocalClassifier
            classifier = LocalClassifier(Path(sys.argv[1]))
        labels, model, version = classifier.predict([text])
        if len(labels) != 1 or labels[0] not in {"FR", "NFR"}:
            raise ValueError()
        response = {
            "requirement_text": text,
            "label": labels[0],
            "model_identifier": model,
            "model_version": version,
            "classified_at": datetime.now(timezone.utc).isoformat(),
            "processing_seconds": time.monotonic() - started,
        }
    except Exception:
        response = {"error": "model_unavailable"}
    print(json.dumps(response, ensure_ascii=True), flush=True)
