"""Lazy loading of an explicitly trusted, locally produced baseline artifact."""
from datetime import datetime, timezone
from pathlib import Path
from threading import Lock
from uuid import uuid4

from intelise_c1.api.classification_schemas import ClassificationRun, Prediction
from intelise_c1.api.extraction_schemas import ExtractionRun

UNAVAILABLE = "FR/NFR classifier unavailable. Configure a trusted locally trained research model and matching baseline dependencies."


class ClassifierUnavailable(Exception):
    """Never contains source texts, model contents or filesystem details."""


class LocalClassifier:
    def __init__(self, directory: Path | None):
        self.directory = directory
        self._loaded = None
        self._lock = Lock()

    def predict(self, texts: list[str]):
        if self.directory is None:
            raise ClassifierUnavailable()
        try:
            with self._lock:
                if self._loaded is None:
                    from intelise_c1.baseline.model import load_artifact
                    self._loaded = load_artifact(self.directory)
                pipeline, metadata = self._loaded
            labels = pipeline.predict(texts).tolist() if texts else []
            return labels, metadata.model_identifier, metadata.model_version
        except Exception:
            # Trusted artifact failures must not take down health or echo texts.
            raise ClassifierUnavailable() from None


def classification_run(extraction: ExtractionRun, labels: list[str], model: str, version: str):
    identifiers = [candidate.requirement_id for candidate in extraction.candidates]
    if len(labels) != len(identifiers) or len(set(identifiers)) != len(identifiers) or any(label not in {"FR", "NFR"} for label in labels):
        raise ClassifierUnavailable()
    now = datetime.now(timezone.utc)
    return ClassificationRun(
        classification_id=str(uuid4()), project_id=extraction.project_id, extraction_run_id=extraction.run_id,
        model_identifier=model, model_version=version,
        classified_at=now.replace(microsecond=now.microsecond // 1000 * 1000),
        predictions=[Prediction(requirement_id=identifier, label=label) for identifier, label in zip(identifiers, labels, strict=True)],
    )
