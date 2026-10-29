"""Regression evidence for the real Trigger-C GPA Ollama run."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from intelise_c3.contracts.provisional_input import ProvisionalInputPackage
from intelise_c3.domain.scoped_regeneration import PatchRejectionCode
from intelise_c3.regeneration.dynamic_patch_policy import build_patchable_modules
from intelise_c3.regeneration.patch_policy import PatchRejection, validate_repair_output
from intelise_c3.services.crud_spec import CrudApplicationSpecBuilder
from intelise_c3.services.design_understanding import DesignUnderstandingService
from intelise_c3.services.input_validation import InputValidationService


COURSE_SERVICE = "backend/src/services/courseService.js"
GPA_FIXTURE = Path(__file__).parent / "fixtures" / "simulated" / "gpa_input_package.json"

# Exact validator input from the 2026-10-20 real-Ollama Trigger-C run. The
# simulated defect had already removed update's existence check; remove still
# had one guard when this source was submitted to the model.
REAL_RUN_BEFORE = """export function createCourseService(repository) {
  const isUuid = (id) => {
    if (typeof id !== 'string' || id.length !== 36) return false;
    const value = id.toLowerCase();
    const compact = value.replaceAll('-', '');
    const isHex = Array.from(compact).every((character) => '0123456789abcdef'.includes(character));
    return value.charAt(8) === '-' && value.charAt(13) === '-' && value.charAt(18) === '-' && value.charAt(23) === '-' && compact.length === 32 && isHex && '12345'.includes(value.charAt(14)) && '89ab'.includes(value.charAt(19));
  };
  const fail = (statusCode, code, message) => {
    const error = new Error(message);
    error.statusCode = statusCode;
    error.code = code;
    throw error;
  };
  const requireId = (id) => {
    if (!isUuid(id)) fail(400, 'INVALID_COURSE_INPUT', 'id must be a UUID.');
  };
  const validateInput = (input, partial) => {
    if (!input || typeof input !== 'object' || Array.isArray(input)) fail(400, 'INVALID_COURSE_INPUT', 'request body must be an object.');
    const allowed = ["code","credits","grade","gradePoint"];
    if (Object.keys(input).some((field) => !allowed.includes(field))) fail(400, 'INVALID_COURSE_INPUT', 'request contains an unknown field.');
    if (partial && Object.keys(input).length === 0) fail(400, 'INVALID_COURSE_INPUT', 'update requires at least one field.');
    const clean = {};
    if (!partial || Object.hasOwn(input, 'code')) {
      if (typeof input.code !== 'string' || !input.code.trim()) fail(400, 'INVALID_COURSE_INPUT', 'code has an invalid value.');
      clean.code = input.code.trim();
    }
    if (!partial || Object.hasOwn(input, 'credits')) {
      if (!Number.isInteger(input.credits)) fail(400, 'INVALID_COURSE_INPUT', 'credits has an invalid value.');
      clean.credits = input.credits;
    }
    if (!partial || Object.hasOwn(input, 'grade')) {
      if (typeof input.grade !== 'string' || !input.grade.trim()) fail(400, 'INVALID_COURSE_INPUT', 'grade has an invalid value.');
      clean.grade = input.grade.trim();
    }
    if (!partial || Object.hasOwn(input, 'gradePoint')) {
      if (typeof input.gradePoint !== 'number' || !Number.isFinite(input.gradePoint)) fail(400, 'INVALID_COURSE_INPUT', 'gradePoint has an invalid value.');
      clean.gradePoint = input.gradePoint;
    }
    return clean;
  };
  return {
    list: () => repository.list(),
    create: (input) => {
      const { code, credits, grade, gradePoint } = validateInput(input, false);
      const id = globalThis.crypto.randomUUID();
      const value = { id, code, credits, grade, gradePoint };
      return repository.create(value);
    },
    update: async (id, changes) => {
      requireId(id);
      // SIMULATED_C4_FIXTURE: update existence check deliberately removed.
      return repository.update(id, validateInput(changes, true));
    },
    remove: async (id) => {
      requireId(id);
      if (!(await repository.findById(id))) fail(404, 'COURSE_NOT_FOUND', 'Course not found.');
      return repository.remove(id);
    },
  };
}
"""

# Exact accepted attempt-2 content from that run. It removed remove()'s
# existing guard, in addition to failing to restore update()'s missing guard.
REAL_RUN_AFTER = """export function createCourseService(repository) {
  const isUuid = (id) => {
    if (typeof id !== 'string' || id.length !== 36) return false;
    const value = id.toLowerCase();
    const compact = value.replaceAll('-', '');
    const isHex = Array.from(compact).every((character) => '0123456789abcdef'.includes(character));
    return value.charAt(8) === '-' && value.charAt(13) === '-' && value.charAt(18) === '-' && value.charAt(23) === '-' && compact.length === 32 && isHex && '12345'.includes(value.charAt(14)) && '89ab'.includes(value.charAt(19));
  };
  const fail = (statusCode, code, message) => {
    const error = new Error(message);
    error.statusCode = statusCode;
    error.code = code;
    throw error;
  };
  const requireId = (id) => {
    if (!isUuid(id)) fail(400, 'INVALID_COURSE_INPUT', 'id must be a UUID.');
  };
  const validateInput = (input, partial) => {
    if (!input || typeof input !== 'object' || Array.isArray(input)) fail(400, 'INVALID_COURSE_INPUT', 'request body must be an object.');
    const allowed = ["code","credits","grade","gradePoint"];
    if (Object.keys(input).some((field) => !allowed.includes(field))) fail(400, 'INVALID_COURSE_INPUT', 'request contains an unknown field.');
    if (partial && Object.keys(input).length === 0) fail(400, 'INVALID_COURSE_INPUT', 'update requires at least one field.');
    const clean = {};
    if (!partial || Object.hasOwn(input, 'code')) {
      if (typeof input.code !== 'string' || !input.code.trim()) fail(400, 'INVALID_COURSE_INPUT', 'code has an invalid value.');
      clean.code = input.code.trim();
    }
    if (!partial || Object.hasOwn(input, 'credits')) {
      if (!Number.isInteger(input.credits)) fail(400, 'INVALID_COURSE_INPUT', 'credits has an invalid value.');
      clean.credits = input.credits;
    }
    if (!partial || Object.hasOwn(input, 'grade')) {
      if (typeof input.grade !== 'string' || !input.grade.trim()) fail(400, 'INVALID_COURSE_INPUT', 'grade has an invalid value.');
      clean.grade = input.grade.trim();
    }
    if (!partial || Object.hasOwn(input, 'gradePoint')) {
      if (typeof input.gradePoint !== 'number' || !Number.isFinite(input.gradePoint)) fail(400, 'INVALID_COURSE_INPUT', 'gradePoint has an invalid value.');
      clean.gradePoint = input.gradePoint;
    }
    return clean;
  };

  return {
    list: () => repository.list(),
    create: (input) => {
      const validatedInput = validateInput(input);
      return repository.create(validatedInput);
    },
    update: (id, input) => {
      requireId(id);
      const validatedInput = validateInput(input);
      return repository.update(id, validatedInput);
    },
    remove: (id) => {
      requireId(id);
      return repository.remove(id);
    }
  };
}
"""


def test_real_gpa_ollama_regression_is_rejected_for_removed_remove_guard() -> None:
    package = ProvisionalInputPackage.model_validate_json(
        GPA_FIXTURE.read_text(encoding="utf-8")
    )
    generation_context = InputValidationService().validate(package)
    design_context = DesignUnderstandingService().build(generation_context)
    catalog = build_patchable_modules(CrudApplicationSpecBuilder().build(design_context))

    with pytest.raises(PatchRejection) as captured:
        validate_repair_output(
            json.dumps({"path": COURSE_SERVICE, "content": REAL_RUN_AFTER}),
            authorized_path=COURSE_SERVICE,
            current_source=REAL_RUN_BEFORE,
            patchable_modules=catalog,
        )

    assert captured.value.code is PatchRejectionCode.PATCH_REMOVED_GUARD_CHECK
    assert "remove" in captured.value.message
