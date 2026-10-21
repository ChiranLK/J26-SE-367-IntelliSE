"""Export the 2.0 hybrid contracts as JSON Schema files under contracts/schemas/.

    .venv\\Scripts\\python.exe scripts\\export_hybrid_schemas.py          # write
    .venv\\Scripts\\python.exe scripts\\export_hybrid_schemas.py --check  # fail if stale
"""

from __future__ import annotations

import json
import sys

from intelise_c3.contracts.hybrid import (
    C1PackageV2,
    C2PackageV2,
    C4DefectFeedback,
    C4ReadinessSignal,
    HumanOverride,
    HybridInputPackage,
    PolicyAcceptance,
)
from intelise_c3.core.config import COMPONENT_ROOT

SCHEMAS = {
    "c1-package-2.0": C1PackageV2,
    "c2-package-2.0": C2PackageV2,
    "hybrid-input-package-2.0": HybridInputPackage,
    "human-override-2.0": HumanOverride,
    "policy-acceptance-2.0": PolicyAcceptance,
    "c4-defect-feedback-2.0": C4DefectFeedback,
    "c4-readiness-signal-2.0": C4ReadinessSignal,
}


def main() -> int:
    target = COMPONENT_ROOT / "contracts" / "schemas"
    target.mkdir(parents=True, exist_ok=True)
    stale = []
    for name, model in SCHEMAS.items():
        text = json.dumps(model.model_json_schema(), indent=2, sort_keys=True) + "\n"
        path = target / f"{name}.schema.json"
        if "--check" in sys.argv:
            if not path.exists() or path.read_text(encoding="utf-8") != text:
                stale.append(path.name)
        else:
            path.write_text(text, encoding="utf-8", newline="\n")
            print(f"wrote {path.relative_to(COMPONENT_ROOT)}")
    if stale:
        print(f"stale schemas: {stale}")
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
