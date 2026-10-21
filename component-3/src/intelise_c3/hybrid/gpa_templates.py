"""Versioned deterministic templates for the GPA domain pack (React + Node.js + PostgreSQL).

Each module renders only from the ``GpaSpec`` slice it depends on. Artifact
bytes never contain run IDs, timestamps or upstream versions (those live in the
generation manifest), so equal inputs give equal hashes and unchanged modules
stay byte-identical across scoped regeneration.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, replace
import json

from intelise_c3.hybrid.gpa_spec import GpaSpec

TEMPLATE_SET_ID = "c3-gpa-react-node-postgres"
TEMPLATE_SET_VERSION = "1.0.0"
TEMPLATE_SET_REF = f"{TEMPLATE_SET_ID}@{TEMPLATE_SET_VERSION}"


@dataclass(frozen=True)
class ModuleTemplate:
    module_id: str
    layer: str
    artifact_type: str
    template_id: str
    uml_classes: tuple[str, ...]
    render: Callable[[GpaSpec], dict[str, str]]
    rag_stack: str
    rag_layer: str


@dataclass(frozen=True)
class ApiOperation:
    operation_id: str
    method: str
    path: str
    uml_bindings: tuple[str, ...]
    requires_persistence: bool = False
    requires_clear_history: bool = False
    #: UML members (Class.method or Class.attribute) the operation exercises; see hybrid/trace_precision.py.
    uml_members: tuple[str, ...] = ()

    def classes(self) -> tuple[str, ...]:
        return tuple(sorted({*self.uml_bindings, *(member.partition(".")[0] for member in self.uml_members)}))


@dataclass(frozen=True)
class DatabaseEntity:
    entity_id: str
    table: str
    uml_class: str


@dataclass(frozen=True)
class TestSeam:
    seam_id: str
    seam_type: str
    module_id: str
    uml_classes: tuple[str, ...]
    reference: str
    description: str
    #: UML members (Class.method or Class.attribute) the seam exercises; see hybrid/trace_precision.py.
    uml_members: tuple[str, ...] = ()

    def classes(self) -> tuple[str, ...]:
        return tuple(sorted({*self.uml_classes, *(member.partition(".")[0] for member in self.uml_members)}))


API_OPERATIONS = (
    ApiOperation("calculateGpa", "POST", "/api/v1/gpa/calculations", ("ModuleResult",), uml_members=("GpaCalculationService.calculate",)),
    ApiOperation("listGpaCalculations", "GET", "/api/v1/gpa/calculations", (), True,
                 uml_members=("GpaCalculationService.listHistory", "GpaCalculationRepository.list")),
    ApiOperation("getGradingPolicy", "GET", "/api/v1/gpa/policy", (),
                 uml_members=("GradingPolicy.gradePoint", "GpaCalculation.policyVersion")),
    ApiOperation("clearGpaHistory", "DELETE", "/api/v1/gpa/calculations", (), True, True,
                 uml_members=("GpaCalculationService.clearHistory", "GpaCalculationRepository.clear")),
)
DATABASE_ENTITIES = (
    DatabaseEntity("DB-gpa_calculations", "gpa_calculations", "GpaCalculation"),
    DatabaseEntity("DB-gpa_calculation_modules", "gpa_calculation_modules", "ModuleResult"),
)
TEST_SEAMS = (
    TestSeam("SEAM-GPA-SERVICE", "SERVICE_INTERFACE", "be.service", (),
             "backend/src/services/gpaCalculationService.js#GpaCalculationService",
             "new GpaCalculationService({ repository, gradingPolicy, clock, idGenerator }).calculate(modules)",
             ("GpaCalculationService.calculate",)),
    TestSeam("SEAM-GPA-REPOSITORY", "INJECTED_REPOSITORY", "be.repository", ("GpaCalculationRepository",),
             "backend/src/repositories/gpaCalculationRepository.js#assertGpaCalculationRepository",
             "Any object with async save(calculation) and list(); InMemoryGpaCalculationRepository is provided."),
    TestSeam("SEAM-GPA-POLICY", "INJECTED_POLICY", "be.policy", ("GradingPolicy",),
             "backend/src/policy/gradingPolicy.js#GradingPolicy",
             "new GradingPolicy(tableOfGradePointTenths, metadata) lets testers control the policy."),
    TestSeam("SEAM-GPA-VALIDATOR", "SERVICE_INTERFACE", "be.validation", ("ModuleResult",),
             "backend/src/validation/gpaRequestValidator.js#validateGpaRequest",
             "validateGpaRequest(body, gradingPolicy) -> { value, errors, review }"),
    TestSeam("SEAM-GPA-API-CALCULATE", "API_CONTRACT", "be.controller", ("ModuleResult",),
             "openapi/openapi.json#calculateGpa", "POST /api/v1/gpa/calculations", ("GpaCalculationService.calculate",)),
    TestSeam("SEAM-GPA-API-HISTORY", "API_CONTRACT", "be.controller", (),
             "openapi/openapi.json#listGpaCalculations", "GET /api/v1/gpa/calculations",
             ("GpaCalculationService.listHistory", "GpaCalculationRepository.list")),
    TestSeam("SEAM-GPA-API-CLEAR", "API_CONTRACT", "be.controller", (),
             "openapi/openapi.json#clearGpaHistory", "DELETE /api/v1/gpa/calculations",
             ("GpaCalculationService.clearHistory", "GpaCalculationRepository.clear")),
    TestSeam("SEAM-GPA-UI-FORM", "FRONTEND_FORM", "fe.gpa-form", ("ModuleResult", "GpaCalculation"),
             "frontend/src/components/GpaCalculatorForm.jsx#data-testid", "data-testid attributes on rows, inputs, buttons and the result"),
)


def _fill(template: str, **values: str) -> str:
    text = template
    for key, value in values.items():
        text = text.replace(f"__{key}__", value)
    if "__" in text and any(f"__{key}__" in text for key in values):
        raise ValueError("unfilled template token")
    return text.strip("\n") + "\n"


def _json(value) -> str:
    return json.dumps(value, indent=2, sort_keys=True)


def operations_for(persistence_required: bool, clear_history: bool = False) -> list[ApiOperation]:
    """The API operations a design needs: history needs persistence, clearing it needs the clearHistory() design."""
    return [
        op
        for op in API_OPERATIONS
        if (persistence_required or not op.requires_persistence) and (clear_history or not op.requires_clear_history)
    ]


def seam_applies(seam: "TestSeam", persistence_required: bool, clear_history: bool) -> bool:
    if seam.seam_id == "SEAM-GPA-API-HISTORY":
        return persistence_required
    if seam.seam_id == "SEAM-GPA-API-CLEAR":
        return persistence_required and clear_history
    return True


def _operations(spec: GpaSpec) -> list[ApiOperation]:
    return operations_for(spec.persistence_required, spec.clear_history)


def constraint_payload(spec: GpaSpec) -> dict:
    code = spec.constraint("ModuleResult.moduleCode")
    credits = spec.constraint("ModuleResult.credits")
    grade = spec.constraint("ModuleResult.grade")
    return {
        "moduleCode": {
            "required": code.required,
            "maxLength": code.max_length,
            "pattern": code.pattern,
            "uniqueWithinRequest": code.unique_within_request,
        },
        "credits": {"required": credits.required, "min": credits.minimum, "max": credits.maximum},
        "grade": {"required": grade.required, "enumFromPolicy": grade.enum_from_policy},
        "maxModules": spec.max_modules,
    }


def _policy_payload(spec: GpaSpec) -> dict:
    policy = spec.policy
    return {
        "policyId": policy.policy_id,
        "policyVersion": policy.policy_version,
        "policyName": policy.policy_name,
        "authorityStatus": policy.authority_status,
        "institution": policy.institution,
        "rounding": {"decimalPlaces": spec.rounding_decimal_places, "mode": spec.rounding_mode},
    }


def _grade_tenths(spec: GpaSpec) -> dict:
    return {entry.grade: entry.grade_point_tenths for entry in spec.policy.grades}


# --------------------------------------------------------------------------- backend


def render_backend_app(spec: GpaSpec) -> dict[str, str]:
    package = {
        "name": "gpa-calculator-backend",
        "private": True,
        "version": "1.0.0",
        "type": "module",
        "engines": {"node": ">=24 <25"},
        "scripts": {"start": "node src/server.js", "test": "node --test test/*.test.js"},
        "dependencies": {"express": "4.22.3", "pg": "8.13.1"},
    }
    errors_js = """
// Shared error type and the KB-API-CONVENTIONS error body: { error: { code, status, message, details } }.
export class AppError extends Error {
  constructor(httpStatus, code, status, message, details = []) {
    super(message);
    this.httpStatus = httpStatus;
    this.code = code;
    this.status = status;
    this.details = details;
  }
}

export function invalidInput(details) {
  return new AppError(400, 'INVALID_INPUT', 'INVALID_INPUT', 'Request validation failed.', details);
}

export function reviewRequired(code, message, details = []) {
  return new AppError(422, code, 'REVIEW_REQUIRED', message, details);
}

export function notFound(message) {
  return new AppError(404, 'NOT_FOUND', 'NOT_FOUND', message);
}

// A service may throw a plain Error carrying one of the KB edge-case codes; map it to the documented HTTP behaviour.
const REVIEW_CODES = new Set(['UNKNOWN_GRADE', 'REPEATED_MODULE_POLICY_UNDEFINED', 'NO_GPA_CREDITS']);
const INVALID_CODES = new Set(['ZERO_CREDIT_NOT_ALLOWED']);

export function translateServiceError(error) {
  if (error instanceof AppError) return error;
  if (error && REVIEW_CODES.has(error.code)) return reviewRequired(error.code, error.message);
  if (error && INVALID_CODES.has(error.code)) return invalidInput([{ field: 'credits', code: error.code, message: error.message }]);
  return error;
}

export function errorMiddleware(error, _req, res, _next) {
  if (error instanceof AppError) {
    res.status(error.httpStatus).json({
      error: { code: error.code, status: error.status, message: error.message, details: error.details },
    });
    return;
  }
  if (error && error.type === 'entity.parse.failed') {
    res.status(400).json({ error: { code: 'MALFORMED_JSON', status: 'INVALID_INPUT', message: 'Request body is not valid JSON.', details: [] } });
    return;
  }
  console.error('unexpected server error:', error && error.message);
  res.status(500).json({ error: { code: 'INTERNAL_ERROR', status: 'INTERNAL', message: 'Unexpected server error.', details: [] } });
}
"""
    app_js = """
// Composition root: the only module that wires routes, controllers, services and repositories.
import express from 'express';
import { createGpaRoutes } from './routes/gpaRoutes.js';
import { createGpaController } from './controllers/gpaController.js';
import { GpaCalculationService } from './services/gpaCalculationService.js';
import { GradingPolicy } from './policy/gradingPolicy.js';
import { assertGpaCalculationRepository } from './repositories/gpaCalculationRepository.js';
import { errorMiddleware, notFound } from './errors.js';
import { randomUUID } from 'node:crypto';

// clock and idGenerator are explicit injection points of GpaCalculationService (test seams for Component 4).
export function createApp({
  repository,
  gradingPolicy = new GradingPolicy(),
  corsOrigin = '',
  healthCheck = async () => 'NOT_CONFIGURED',
  clock = () => new Date(),
  idGenerator = () => randomUUID(),
}) {
  assertGpaCalculationRepository(repository);
  const service = new GpaCalculationService({ repository, gradingPolicy, clock, idGenerator });
  const controller = createGpaController({ service, gradingPolicy });
  const app = express();
  app.disable('x-powered-by');
  app.use(express.json({ limit: '32kb' }));
  app.use((req, res, next) => {
    if (corsOrigin) {
      res.setHeader('Access-Control-Allow-Origin', corsOrigin);
      res.setHeader('Vary', 'Origin');
      res.setHeader('Access-Control-Allow-Headers', 'Content-Type');
      res.setHeader('Access-Control-Allow-Methods', '__CORS_METHODS__');
    }
    if (req.method === 'OPTIONS') {
      res.status(204).end();
      return;
    }
    next();
  });
  app.get('/api/health', async (_req, res) => {
    try {
      const database = await healthCheck();
      res.json({ status: 'UP', database });
    } catch {
      res.status(503).json({ status: 'DOWN', database: 'DOWN' });
    }
  });
  app.use('/api/v1', createGpaRoutes(controller));
  app.use((_req, _res, next) => next(notFound('Route not found.')));
  app.use(errorMiddleware);
  return app;
}
"""
    server_js = """
// Process entry point. Configuration comes only from the environment of the disposable container.
import { createApp } from './app.js';
import { createPool } from './db/pool.js';
import { applyMigrations } from './db/migrate.js';
import { PostgresGpaCalculationRepository } from './repositories/postgresGpaCalculationRepository.js';
import { InMemoryGpaCalculationRepository } from './repositories/inMemoryGpaCalculationRepository.js';

const host = process.env.HOST || '127.0.0.1';
const port = Number(process.env.PORT || 3001);
const persistence = process.env.PERSISTENCE || 'postgres';

async function main() {
  let repository;
  let healthCheck = async () => 'IN_MEMORY';
  if (persistence === 'postgres') {
    const pool = createPool(process.env);
    await applyMigrations(pool);
    repository = new PostgresGpaCalculationRepository({ pool });
    healthCheck = async () => {
      await pool.query('SELECT 1');
      return 'UP';
    };
  } else {
    repository = new InMemoryGpaCalculationRepository();
  }
  const app = createApp({ repository, corsOrigin: process.env.CORS_ALLOWED_ORIGIN || '', healthCheck });
  app.listen(port, host, () => {
    console.log(`gpa backend listening on ${host}:${port} (persistence=${persistence})`);
  });
}

main().catch((error) => {
  console.error('gpa backend failed to start:', error.message);
  process.exit(1);
});
"""
    pool_js = """
// Database boundary: only repositories receive this pool.
import pg from 'pg';

export function createPool(env) {
  const pool = new pg.Pool({
    host: env.PGHOST,
    port: Number(env.PGPORT || 5432),
    user: env.PGUSER,
    password: env.PGPASSWORD,
    database: env.PGDATABASE,
    max: 5,
    connectionTimeoutMillis: 5000,
  });
  // The database can end an idle connection (restart, stop). Without a listener Node treats that 'error' event as
  // fatal and the API process exits; with it the API keeps answering and the pool opens a new connection on demand.
  pool.on('error', (error) => {
    console.error('database connection error (the pool reconnects on the next query):', error.message);
  });
  return pool;
}
"""
    migrate_js = """
// Forward-only migrations from database/migrations, applied once each inside the disposable environment.
import { readdir, readFile } from 'node:fs/promises';
import path from 'node:path';
import { fileURLToPath } from 'node:url';

const MIGRATIONS_DIR = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '../../../database/migrations');

export async function applyMigrations(pool, directory = MIGRATIONS_DIR) {
  let lastError;
  for (let attempt = 1; attempt <= 30; attempt += 1) {
    try {
      await pool.query('SELECT 1');
      lastError = undefined;
      break;
    } catch (error) {
      lastError = error;
      await new Promise((resolve) => setTimeout(resolve, 1000));
    }
  }
  if (lastError) throw lastError;
  await pool.query('CREATE TABLE IF NOT EXISTS schema_migrations (name TEXT PRIMARY KEY, applied_at TIMESTAMPTZ NOT NULL DEFAULT now())');
  const files = (await readdir(directory)).filter((name) => name.endsWith('.sql')).sort();
  for (const name of files) {
    const done = await pool.query('SELECT 1 FROM schema_migrations WHERE name = $1', [name]);
    if (done.rowCount) continue;
    const sql = await readFile(path.join(directory, name), 'utf8');
    await pool.query('BEGIN');
    try {
      await pool.query(sql);
      await pool.query('INSERT INTO schema_migrations (name) VALUES ($1)', [name]);
      await pool.query('COMMIT');
    } catch (error) {
      await pool.query('ROLLBACK');
      throw error;
    }
  }
}
"""
    return {
        "backend/package.json": _json(package) + "\n",
        "backend/src/errors.js": _fill(errors_js),
        "backend/src/app.js": _fill(app_js, CORS_METHODS="GET,POST,DELETE,OPTIONS" if spec.clear_history else "GET,POST,OPTIONS"),
        "backend/src/server.js": _fill(server_js),
        "backend/src/db/pool.js": _fill(pool_js),
        "backend/src/db/migrate.js": _fill(migrate_js),
    }


def render_backend_policy(spec: GpaSpec) -> dict[str, str]:
    template = """
// Generated from KB-GPA-GRADE-SCALE. Grade points are Knowledge Base facts, never model output.
// Authority: __AUTHORITY__ - see POLICY.authorityStatus before relying on any result.
export const POLICY = Object.freeze(__POLICY__);

const GRADE_POINT_TENTHS = Object.freeze(__TABLE__);

// @c3-uml GradingPolicy
export class GradingPolicy {
  constructor(table = GRADE_POINT_TENTHS, metadata = POLICY) {
    this.table = Object.freeze({ ...table });
    this.meta = Object.freeze({ ...metadata });
  }

  gradePoint(grade) {
    const tenths = this.gradePointTenths(grade);
    return tenths === null ? null : tenths / 10;
  }

  gradePointTenths(grade) {
    return Object.prototype.hasOwnProperty.call(this.table, grade) ? this.table[grade] : null;
  }

  grades() {
    return Object.keys(this.table);
  }

  metadata() {
    return this.meta;
  }
}
"""
    return {
        "backend/src/policy/gradingPolicy.js": _fill(
            template,
            AUTHORITY=spec.policy.authority_status,
            POLICY=_json(_policy_payload(spec)),
            TABLE=_json(_grade_tenths(spec)),
        )
    }


def render_backend_validation(spec: GpaSpec) -> dict[str, str]:
    template = """
// Request validation boundary. Constraints come from approved C1 requirement constraints,
// falling back to KB-GPA-VALIDATION-DEFAULTS only where C1 supplied none.
export const CONSTRAINTS = Object.freeze(__CONSTRAINTS__);

const CODE_PATTERN = CONSTRAINTS.moduleCode.pattern ? new RegExp(CONSTRAINTS.moduleCode.pattern) : null;

function fieldError(index, field, code, message) {
  return { index, field, code, message };
}

export function validateGpaRequest(body, gradingPolicy) {
  const errors = [];
  const review = [];
  const modules = body && Array.isArray(body.modules) ? body.modules : null;
  if (!modules || modules.length === 0) {
    errors.push(fieldError(null, 'modules', 'MODULES_REQUIRED', 'Provide at least one module result.'));
    return { value: null, errors, review };
  }
  if (modules.length > CONSTRAINTS.maxModules) {
    errors.push(fieldError(null, 'modules', 'TOO_MANY_MODULES', `At most ${CONSTRAINTS.maxModules} modules are accepted.`));
    return { value: null, errors, review };
  }
  const normalized = [];
  const seenCodes = new Map();
  modules.forEach((raw, index) => {
    const item = raw && typeof raw === 'object' ? raw : {};
    const moduleCode = typeof item.moduleCode === 'string' ? item.moduleCode.trim() : '';
    if (CONSTRAINTS.moduleCode.required && !moduleCode) {
      errors.push(fieldError(index, 'moduleCode', 'MODULE_CODE_REQUIRED', 'Module code is required.'));
    } else if (CONSTRAINTS.moduleCode.maxLength && moduleCode.length > CONSTRAINTS.moduleCode.maxLength) {
      errors.push(fieldError(index, 'moduleCode', 'MODULE_CODE_TOO_LONG', `Module code is longer than ${CONSTRAINTS.moduleCode.maxLength} characters.`));
    } else if (CODE_PATTERN && !CODE_PATTERN.test(moduleCode)) {
      errors.push(fieldError(index, 'moduleCode', 'MODULE_CODE_PATTERN', `Module code must match ${CONSTRAINTS.moduleCode.pattern}.`));
    }
    const credits = item.credits;
    if (credits === 0) {
      errors.push(fieldError(index, 'credits', 'ZERO_CREDIT_NOT_ALLOWED', 'A module counted toward GPA cannot have zero credits.'));
    } else if (!Number.isInteger(credits) || credits < CONSTRAINTS.credits.min || credits > CONSTRAINTS.credits.max) {
      errors.push(fieldError(index, 'credits', 'CREDITS_OUT_OF_RANGE', `Credits must be a whole number from ${CONSTRAINTS.credits.min} to ${CONSTRAINTS.credits.max}.`));
    }
    const grade = typeof item.grade === 'string' ? item.grade.trim() : '';
    if (!grade) {
      errors.push(fieldError(index, 'grade', 'GRADE_REQUIRED', 'Grade is required.'));
    } else if (gradingPolicy.gradePointTenths(grade) === null) {
      review.push(fieldError(index, 'grade', 'UNKNOWN_GRADE', `Grade '${grade}' is not defined by the accepted grading policy; no grade point is guessed.`));
    }
    if (item.countsTowardGpa !== undefined && typeof item.countsTowardGpa !== 'boolean') {
      errors.push(fieldError(index, 'countsTowardGpa', 'COUNTS_TOWARD_GPA_BOOLEAN', 'countsTowardGpa must be true or false.'));
    }
    if (moduleCode) {
      const key = moduleCode.toUpperCase();
      if (seenCodes.has(key)) {
        review.push(fieldError(index, 'moduleCode', 'REPEATED_MODULE_POLICY_UNDEFINED', `Module ${moduleCode} appears more than once; the accepted policy does not define how repeated attempts combine.`));
      }
      seenCodes.set(key, index);
    }
    normalized.push({ moduleCode, credits, grade, countsTowardGpa: item.countsTowardGpa !== false });
  });
  return { value: { modules: normalized }, errors, review };
}
"""
    return {
        "backend/src/validation/gpaRequestValidator.js": _fill(template, CONSTRAINTS=_json(constraint_payload(spec)))
    }


def render_backend_service(spec: GpaSpec) -> dict[str, str]:
    template = """
// Credit-weighted GPA (KB-GPA-FORMULA) with exact integer arithmetic and KB-GPA-ROUNDING.
// Edge cases follow KB-GPA-UNKNOWN-GRADE, KB-GPA-ZERO-CREDIT, KB-GPA-NON-GPA-MODULES and KB-GPA-REPEATED-MODULES.
import { randomUUID } from 'node:crypto';
import { invalidInput, reviewRequired } from '../errors.js';

const DECIMAL_PLACES = __DECIMALS__;

// Round numerator/denominator half-up to DECIMAL_PLACES using integers only.
export function roundHalfUp(numerator, denominator, decimals = DECIMAL_PLACES) {
  const scale = 10 ** decimals;
  const scaled = Math.floor((2 * numerator * scale + denominator) / (2 * denominator));
  return { value: scaled / scale, text: (scaled / scale).toFixed(decimals) };
}

export function computeGpa(modules, gradingPolicy) {
  let weightedTenths = 0;
  let totalCredits = 0;
  const seen = new Set();
  const lines = modules.map((module, index) => {
    const tenths = gradingPolicy.gradePointTenths(module.grade);
    if (tenths === null) {
      throw reviewRequired('UNKNOWN_GRADE', `Grade '${module.grade}' is not defined by the accepted grading policy.`, [{ index, field: 'grade' }]);
    }
    const key = String(module.moduleCode).toUpperCase();
    if (seen.has(key)) {
      throw reviewRequired('REPEATED_MODULE_POLICY_UNDEFINED', `Module ${module.moduleCode} is repeated; the accepted policy does not define how attempts combine.`, [{ index, field: 'moduleCode' }]);
    }
    seen.add(key);
    const counts = module.countsTowardGpa !== false;
    if (counts) {
      if (!Number.isInteger(module.credits) || module.credits <= 0) {
        throw invalidInput([{ index, field: 'credits', code: 'ZERO_CREDIT_NOT_ALLOWED', message: 'Counted modules need positive whole credits.' }]);
      }
      weightedTenths += module.credits * tenths;
      totalCredits += module.credits;
    }
    return { moduleCode: module.moduleCode, credits: module.credits, grade: module.grade, gradePoint: tenths / 10, countsTowardGpa: counts };
  });
  if (totalCredits === 0) {
    throw reviewRequired('NO_GPA_CREDITS', 'No module counts toward GPA, so no GPA value is produced.');
  }
  const rounded = roundHalfUp(weightedTenths, totalCredits * 10);
  return { gpa: rounded.value, gpaText: rounded.text, totalCredits, weightedGradePoints: weightedTenths / 10, modules: lines };
}

// @c3-uml GpaCalculationService
export class GpaCalculationService {
  constructor({ repository, gradingPolicy, clock = () => new Date(), idGenerator = () => randomUUID() }) {
    this.repository = repository;
    this.gradingPolicy = gradingPolicy;
    this.clock = clock;
    this.idGenerator = idGenerator;
  }

  async calculate(modules) {
    const result = computeGpa(modules, this.gradingPolicy);
    const policy = this.gradingPolicy.metadata();
    const calculation = {
      id: this.idGenerator(),
      policyId: policy.policyId,
      policyVersion: policy.policyVersion,
      policyAuthorityStatus: policy.authorityStatus,
      totalCredits: result.totalCredits,
      gpa: result.gpa,
      gpaText: result.gpaText,
      weightedGradePoints: result.weightedGradePoints,
      createdAt: this.clock().toISOString(),
      modules: result.modules,
    };
    return __SAVE__;
  }

  async listHistory() {
    return __LIST__;
  }
__CLEAR__}
"""
    clear = "\n  async clearHistory() {\n    await this.repository.clear();\n  }\n" if spec.clear_history else ""
    save = "this.repository.save(calculation)" if spec.persistence_required else "calculation"
    listing = "this.repository.list()" if spec.persistence_required else "[]"
    return {
        "backend/src/services/gpaCalculationService.js": _fill(
            template, DECIMALS=str(spec.rounding_decimal_places), SAVE=save, LIST=listing, CLEAR=clear
        )
    }


def render_backend_repository(spec: GpaSpec) -> dict[str, str]:
    contract = """
// Repository seam (SEAM-GPA-REPOSITORY): services depend on this shape, never on a concrete database.
export const GPA_CALCULATION_REPOSITORY_METHODS = Object.freeze([__METHODS__]);

export function assertGpaCalculationRepository(repository) {
  for (const method of GPA_CALCULATION_REPOSITORY_METHODS) {
    if (!repository || typeof repository[method] !== 'function') {
      throw new TypeError(`GPA calculation repository must implement ${method}()`);
    }
  }
  return repository;
}
"""
    memory = """
// In-memory implementation of the repository seam (used by smoke checks and C4 fakes).
// @c3-uml GpaCalculationRepository
export class InMemoryGpaCalculationRepository {
  constructor() {
    this.items = [];
  }

  async save(calculation) {
    const copy = structuredClone(calculation);
    this.items.push(copy);
    return structuredClone(copy);
  }

  async list() {
    return this.items
      .slice()
      .sort((a, b) => (a.createdAt < b.createdAt ? 1 : a.createdAt > b.createdAt ? -1 : 0))
      .map((item) => structuredClone(item));
  }
__CLEAR__}
"""
    postgres = """
// PostgreSQL implementation. Only repositories issue SQL, and every statement is parameterized.
// @c3-uml GpaCalculationRepository
export class PostgresGpaCalculationRepository {
  constructor({ pool }) {
    this.pool = pool;
  }

  async save(calculation) {
    const client = await this.pool.connect();
    try {
      await client.query('BEGIN');
      await client.query(
        'INSERT INTO gpa_calculations (id, policy_id, policy_version, total_credits, gpa, created_at) VALUES ($1, $2, $3, $4, $5, $6)',
        [calculation.id, calculation.policyId, calculation.policyVersion, calculation.totalCredits, calculation.gpaText, calculation.createdAt],
      );
      for (const [position, module] of calculation.modules.entries()) {
        await client.query(
          'INSERT INTO gpa_calculation_modules (calculation_id, position, module_code, credits, grade, grade_point, counts_toward_gpa) VALUES ($1, $2, $3, $4, $5, $6, $7)',
          [calculation.id, position, module.moduleCode, module.credits, module.grade, module.gradePoint, module.countsTowardGpa],
        );
      }
      await client.query('COMMIT');
      return calculation;
    } catch (error) {
      await client.query('ROLLBACK');
      throw error;
    } finally {
      client.release();
    }
  }

  async list() {
    const calculations = await this.pool.query(
      'SELECT id, policy_id, policy_version, total_credits, gpa::text AS gpa_text, created_at FROM gpa_calculations ORDER BY created_at DESC LIMIT 50',
    );
    if (calculations.rowCount === 0) return [];
    const modules = await this.pool.query(
      'SELECT calculation_id, module_code, credits, grade, grade_point::float8 AS grade_point, counts_toward_gpa FROM gpa_calculation_modules WHERE calculation_id = ANY($1::uuid[]) ORDER BY position',
      [calculations.rows.map((row) => row.id)],
    );
    return calculations.rows.map((row) => ({
      id: row.id,
      policyId: row.policy_id,
      policyVersion: row.policy_version,
      totalCredits: row.total_credits,
      gpa: Number(row.gpa_text),
      gpaText: row.gpa_text,
      createdAt: new Date(row.created_at).toISOString(),
      modules: modules.rows
        .filter((module) => module.calculation_id === row.id)
        .map((module) => ({
          moduleCode: module.module_code,
          credits: module.credits,
          grade: module.grade,
          gradePoint: module.grade_point,
          countsTowardGpa: module.counts_toward_gpa,
        })),
    }));
  }
__CLEAR__}
"""
    memory_clear = "\n  async clear() {\n    this.items = [];\n  }\n" if spec.clear_history else ""
    # The module rows go with their calculation through the ON DELETE CASCADE foreign key of the migration.
    postgres_clear = "\n  async clear() {\n    await this.pool.query('DELETE FROM gpa_calculations');\n  }\n" if spec.clear_history else ""
    return {
        "backend/src/repositories/gpaCalculationRepository.js": _fill(
            contract, METHODS="'save', 'list', 'clear'" if spec.clear_history else "'save', 'list'"
        ),
        "backend/src/repositories/inMemoryGpaCalculationRepository.js": _fill(memory, CLEAR=memory_clear),
        "backend/src/repositories/postgresGpaCalculationRepository.js": _fill(postgres, CLEAR=postgres_clear),
    }


def render_backend_controller(spec: GpaSpec) -> dict[str, str]:
    template = """
// Controller: HTTP <-> service translation only. It never touches repositories or the database.
import { validateGpaRequest } from '../validation/gpaRequestValidator.js';
import { invalidInput, reviewRequired, translateServiceError } from '../errors.js';

export function createGpaController({ service, gradingPolicy }) {
  return {
    async calculate(req, res) {
      const { value, errors, review } = validateGpaRequest(req.body, gradingPolicy);
      if (errors.length) throw invalidInput(errors);
      if (review.length) throw reviewRequired(review[0].code, review[0].message, review);
      let calculation;
      try {
        calculation = await service.calculate(value.modules);
      } catch (error) {
        throw translateServiceError(error);
      }
      res.status(201).json(calculation);
    },
__LIST_HANDLER__
    async policy(_req, res) {
      res.json({ ...gradingPolicy.metadata(), grades: gradingPolicy.grades().map((grade) => ({ grade, gradePoint: gradingPolicy.gradePoint(grade) })) });
    },
  };
}
"""
    handler = (
        "    async listHistory(_req, res) {\n"
        "      res.json({ items: await service.listHistory() });\n"
        "    },"
        if spec.persistence_required
        else ""
    )
    if spec.clear_history:
        handler += (
            "\n    async clearHistory(_req, res) {\n"
            "      await service.clearHistory();\n"
            "      res.status(204).end();\n"
            "    },"
        )
    return {"backend/src/controllers/gpaController.js": _fill(template, LIST_HANDLER=handler)}


def render_backend_routes(spec: GpaSpec) -> dict[str, str]:
    template = """
// Routes: path -> controller handler only (Route -> Controller -> Service -> Repository -> Database).
import { Router } from 'express';

const handle = (fn) => (req, res, next) => Promise.resolve(fn(req, res)).catch(next);

export function createGpaRoutes(controller) {
  const router = Router();
  router.post('/gpa/calculations', handle(controller.calculate)); // operationId: calculateGpa
__LIST_ROUTE__
  router.get('/gpa/policy', handle(controller.policy)); // operationId: getGradingPolicy
  return router;
}
"""
    route = (
        "  router.get('/gpa/calculations', handle(controller.listHistory)); // operationId: listGpaCalculations"
        if spec.persistence_required
        else ""
    )
    if spec.clear_history:
        route += "\n  router.delete('/gpa/calculations', handle(controller.clearHistory)); // operationId: clearGpaHistory"
    return {"backend/src/routes/gpaRoutes.js": _fill(template, LIST_ROUTE=route)}


COMPOSED_APP_TEST_JS = """
// C3-owned SMOKE CHECK of the composed application (routes -> controller -> service -> repository), over real HTTP on loopback.
// It catches wiring mistakes that module-level tests cannot (for example a missing injected dependency).
// Not a Component 4 test and not independent verification evidence.
import test from 'node:test';
import assert from 'node:assert/strict';
import { createApp } from '../src/app.js';
import { InMemoryGpaCalculationRepository } from '../src/repositories/inMemoryGpaCalculationRepository.js';

const MODULES = [
  { moduleCode: 'IT1010', credits: 4, grade: 'A', countsTowardGpa: true },
  { moduleCode: 'IT1020', credits: 3, grade: 'B+', countsTowardGpa: true },
  { moduleCode: 'IT1030', credits: 2, grade: 'C', countsTowardGpa: true },
  { moduleCode: 'IT1040', credits: 3, grade: 'A-', countsTowardGpa: true },
];

async function withServer(run) {
  const app = createApp({ repository: new InMemoryGpaCalculationRepository() });
  const server = await new Promise((resolve) => {
    const listening = app.listen(0, '127.0.0.1', () => resolve(listening));
  });
  try {
    return await run(`http://127.0.0.1:${server.address().port}`);
  } finally {
    await new Promise((resolve) => server.close(resolve));
  }
}

const post = (base, body) => fetch(`${base}/api/v1/gpa/calculations`, { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(body) });

test('composed app answers the known GPA example over HTTP', async () => {
  await withServer(async (base) => {
    const response = await post(base, { modules: MODULES });
    assert.equal(response.status, 201, await response.clone().text());
    const body = await response.json();
    assert.equal(body.gpaText, '3.42');
    assert.equal(body.totalCredits, 12);
    assert.ok(body.id && body.createdAt, 'id and createdAt come from the injected idGenerator and clock');
  });
});

test('composed app maps edge cases to the documented HTTP behaviour', async () => {
  await withServer(async (base) => {
    const unknown = await post(base, { modules: [{ moduleCode: 'IT1010', credits: 3, grade: 'Z' }] });
    assert.equal(unknown.status, 422);
    assert.equal((await unknown.json()).error.code, 'UNKNOWN_GRADE');
    const invalid = await post(base, { modules: [{ moduleCode: 'IT1010', credits: 99, grade: 'A' }] });
    assert.equal(invalid.status, 400);
    const history = await fetch(`${base}/api/v1/gpa/calculations`);
    assert.equal(history.status, 200);
  });
});
"""


CLEAR_COMPOSED_TEST_JS = """

test('the history can be cleared over HTTP', async () => {
  await withServer(async (base) => {
    await post(base, { modules: MODULES });
    const before = await (await fetch(`${base}/api/v1/gpa/calculations`)).json();
    assert.equal(before.items.length, 1);
    const cleared = await fetch(`${base}/api/v1/gpa/calculations`, { method: 'DELETE' });
    assert.equal(cleared.status, 204);
    const after = await (await fetch(`${base}/api/v1/gpa/calculations`)).json();
    assert.deepEqual(after.items, []);
  });
});
"""


def _composed_test(spec: GpaSpec) -> str:
    return _fill(COMPOSED_APP_TEST_JS) + (CLEAR_COMPOSED_TEST_JS.lstrip("\n") if spec.clear_history else "")


def render_backend_smoke_llm(spec: GpaSpec) -> dict[str, str]:
    """Smoke test for LLM-written backend logic: only the public interfaces + the shared benchmark cases.

    The template smoke test imports template-only helpers (roundHalfUp, CONSTRAINTS), which an LLM module
    need not export. These cases are the same ones the pipeline ran in its sandbox, run again here against the
    files that are actually shipped, during the Docker preview build.
    """
    from intelise_c3.hybrid.llm_sandbox import BENCH_RUNNER_MJS, service_spec, validation_spec

    cases = (
        "// Benchmark cases (gpa-backend-bench-1). Generated by InteliSE Component 3; SMOKE CHECKS, not Component 4 tests.\n"
        f"export const SERVICE_SPEC = {_json(service_spec(spec, 'unused'))};\n\n"
        f"export const VALIDATION_SPEC = {_json(validation_spec(spec, 'unused'))};\n"
    )
    test = """
// C3-owned generated-application SMOKE CHECKS (run during the Docker build).
// These are not Component 4 tests and are not independent verification evidence.
import test from 'node:test';
import assert from 'node:assert/strict';
import { GpaCalculationService } from '../src/services/gpaCalculationService.js';
import { validateGpaRequest } from '../src/validation/gpaRequestValidator.js';
import { runServiceCases, runValidationCases } from './bench-runner.mjs';
import { SERVICE_SPEC, VALIDATION_SPEC } from './bench-cases.mjs';

test('GpaCalculationService passes the benchmark cases', async () => {
  const results = await runServiceCases(GpaCalculationService, SERVICE_SPEC);
  for (const result of results) assert.equal(result.passed, true, `${result.id}: ${result.observed}`);
});

test('validateGpaRequest passes the benchmark cases', async () => {
  const results = await runValidationCases(validateGpaRequest, VALIDATION_SPEC);
  for (const result of results) assert.equal(result.passed, true, `${result.id}: ${result.observed}`);
});
"""
    return {
        "backend/test/bench-cases.mjs": cases,
        "backend/test/bench-runner.mjs": BENCH_RUNNER_MJS.strip("\n") + "\n",
        "backend/test/gpa.smoke.test.js": _fill(test),
        "backend/test/composed-app.smoke.test.js": _composed_test(spec),
    }


def render_backend_smoke(spec: GpaSpec) -> dict[str, str]:
    if spec.llm_backend_logic:
        return render_backend_smoke_llm(spec)
    template = """
// C3-owned generated-application SMOKE CHECKS (run during the Docker build).
// These are not Component 4 tests and are not independent verification evidence.
import test from 'node:test';
import assert from 'node:assert/strict';
import { GpaCalculationService, roundHalfUp } from '../src/services/gpaCalculationService.js';
import { GradingPolicy } from '../src/policy/gradingPolicy.js';
import { InMemoryGpaCalculationRepository } from '../src/repositories/inMemoryGpaCalculationRepository.js';
import { validateGpaRequest, CONSTRAINTS } from '../src/validation/gpaRequestValidator.js';

const policy = new GradingPolicy();
const fixedClock = () => new Date('2026-01-01T00:00:00.000Z');
const service = () => new GpaCalculationService({ repository: new InMemoryGpaCalculationRepository(), gradingPolicy: policy, clock: fixedClock, idGenerator: () => '00000000-0000-4000-8000-000000000000' });
const VALID_CODE = __VALID_CODE__;

test('known credit-weighted GPA example', async () => {
  const result = await service().calculate([
    { moduleCode: VALID_CODE + '1', credits: 4, grade: 'A', countsTowardGpa: true },
    { moduleCode: VALID_CODE + '2', credits: 3, grade: 'B+', countsTowardGpa: true },
    { moduleCode: VALID_CODE + '3', credits: 2, grade: 'C', countsTowardGpa: true },
    { moduleCode: VALID_CODE + '4', credits: 3, grade: 'A-', countsTowardGpa: true },
  ]);
  assert.equal(result.gpaText, '3.42');
  assert.equal(result.totalCredits, 12);
});

test('half-up rounding uses integers', () => {
  assert.equal(roundHalfUp(3335, 1000, 2).text, '3.34');
  assert.equal(roundHalfUp(3334, 1000, 2).text, '3.33');
});

test('unknown grade requires review instead of a guessed value', () => {
  const { review } = validateGpaRequest({ modules: [{ moduleCode: VALID_CODE + '1', credits: 3, grade: 'Z' }] }, policy);
  assert.equal(review[0].code, 'UNKNOWN_GRADE');
});

test('repeated module requires review', () => {
  const { review } = validateGpaRequest({ modules: [
    { moduleCode: VALID_CODE + '1', credits: 3, grade: 'A' },
    { moduleCode: VALID_CODE + '1', credits: 3, grade: 'B' },
  ] }, policy);
  assert.equal(review[0].code, 'REPEATED_MODULE_POLICY_UNDEFINED');
});

test('credit range comes from the approved constraint', () => {
  const tooMany = validateGpaRequest({ modules: [{ moduleCode: VALID_CODE + '1', credits: CONSTRAINTS.credits.max + 1, grade: 'A' }] }, policy);
  assert.equal(tooMany.errors[0].code, 'CREDITS_OUT_OF_RANGE');
  const zero = validateGpaRequest({ modules: [{ moduleCode: VALID_CODE + '1', credits: 0, grade: 'A' }] }, policy);
  assert.equal(zero.errors[0].code, 'ZERO_CREDIT_NOT_ALLOWED');
});

test('non-GPA modules are excluded and all-excluded input requires review', async () => {
  const result = await service().calculate([
    { moduleCode: VALID_CODE + '1', credits: 4, grade: 'A', countsTowardGpa: true },
    { moduleCode: VALID_CODE + '2', credits: 2, grade: 'E', countsTowardGpa: false },
  ]);
  assert.equal(result.gpaText, '4.00');
  await assert.rejects(service().calculate([{ moduleCode: VALID_CODE + '1', credits: 2, grade: 'A', countsTowardGpa: false }]), /No module counts toward GPA/);
});
"""
    # "IT101" + one digit is a SLIIT-style module code (e.g. IT1011) and satisfies the demo fixtures' patterns.
    if spec.clear_history:
        template += """
test('clearHistory empties the repository', async () => {
  const subject = service();
  await subject.calculate([{ moduleCode: VALID_CODE + '1', credits: 4, grade: 'A', countsTowardGpa: true }]);
  assert.equal((await subject.listHistory()).length, 1);
  await subject.clearHistory();
  assert.deepEqual(await subject.listHistory(), []);
});
"""
    return {
        "backend/test/gpa.smoke.test.js": _fill(template, VALID_CODE=json.dumps("IT101")),
        "backend/test/composed-app.smoke.test.js": _composed_test(spec),
    }


# --------------------------------------------------------------------------- database and API


_SQL_TYPES = {"String": "TEXT", "Integer": "INTEGER", "Number": "NUMERIC", "Boolean": "BOOLEAN", "DateTime": "TIMESTAMPTZ"}


def render_database(spec: GpaSpec) -> dict[str, str]:
    credits = spec.constraint("ModuleResult.credits")
    code = spec.constraint("ModuleResult.moduleCode")
    unique = "\n  , UNIQUE (calculation_id, module_code)" if code.unique_within_request else ""
    scale = spec.policy.scale_maximum
    sql = f"""
-- Generated by C3 rule R-DB-001 from released UML entities GpaCalculation and ModuleResult.
-- Ranges mirror approved C1 constraints; grade points come from the accepted KB policy.
CREATE TABLE IF NOT EXISTS gpa_calculations (
  id UUID PRIMARY KEY,
  policy_id TEXT NOT NULL,
  policy_version TEXT NOT NULL,
  total_credits INTEGER NOT NULL CHECK (total_credits > 0),
  gpa NUMERIC(4, {spec.rounding_decimal_places}) NOT NULL CHECK (gpa >= 0 AND gpa <= {scale}),
  created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS gpa_calculation_modules (
  calculation_id UUID NOT NULL REFERENCES gpa_calculations(id) ON DELETE CASCADE,
  position INTEGER NOT NULL CHECK (position >= 0),
  module_code TEXT NOT NULL{f" CHECK (char_length(module_code) <= {code.max_length})" if code.max_length else ""},
  credits INTEGER NOT NULL CHECK (credits BETWEEN {credits.minimum} AND {credits.maximum}),
  grade TEXT NOT NULL,
  grade_point NUMERIC(3, 1) NOT NULL CHECK (grade_point >= 0 AND grade_point <= {scale}),
  counts_toward_gpa BOOLEAN NOT NULL DEFAULT TRUE,
  PRIMARY KEY (calculation_id, position){unique}
);

CREATE INDEX IF NOT EXISTS gpa_calculations_created_at_idx ON gpa_calculations (created_at DESC);
"""
    return {"database/migrations/001_create_gpa_calculations.sql": sql.strip("\n") + "\n"}


def _schema_for(fields, type_map: dict[str, str]) -> dict:
    properties = {}
    for item in fields:
        schema: dict = {"type": type_map[item.uml_type]}
        if item.uml_type == "DateTime":
            schema["format"] = "date-time"
        properties[item.name] = schema
    return properties


def render_openapi(spec: GpaSpec) -> dict[str, str]:
    json_types = {"String": "string", "Integer": "integer", "Number": "number", "Boolean": "boolean", "DateTime": "string"}
    constraints = constraint_payload(spec)
    module_props = _schema_for(spec.module_result_fields, json_types)
    code_schema = module_props["moduleCode"]
    if constraints["moduleCode"]["maxLength"]:
        code_schema["maxLength"] = constraints["moduleCode"]["maxLength"]
    if constraints["moduleCode"]["pattern"]:
        code_schema["pattern"] = constraints["moduleCode"]["pattern"]
    module_props["credits"].update({"minimum": constraints["credits"]["min"], "maximum": constraints["credits"]["max"]})
    module_props["grade"]["enum"] = [entry.grade for entry in spec.policy.grades]
    calc_props = _schema_for(spec.calculation_fields, json_types)
    calc_props.update(
        {
            "gpaText": {"type": "string"},
            "policyAuthorityStatus": {"type": "string"},
            "weightedGradePoints": {"type": "number"},
            "modules": {"type": "array", "items": {"$ref": "#/components/schemas/ModuleResult"}},
        }
    )
    error_ref = {"$ref": "#/components/schemas/ErrorResponse"}
    paths: dict = {
        "/api/v1/gpa/calculations": {
            "post": {
                "operationId": "calculateGpa",
                "summary": "Calculate a credit-weighted GPA",
                "requestBody": {"required": True, "content": {"application/json": {"schema": {"$ref": "#/components/schemas/GpaCalculationRequest"}}}},
                "responses": {
                    "201": {"description": "Calculated", "content": {"application/json": {"schema": {"$ref": "#/components/schemas/GpaCalculation"}}}},
                    "400": {"description": "Invalid input", "content": {"application/json": {"schema": error_ref}}},
                    "422": {"description": "Review required (unknown grade, repeated module, no GPA credits)", "content": {"application/json": {"schema": error_ref}}},
                },
            }
        },
        "/api/v1/gpa/policy": {
            "get": {
                "operationId": "getGradingPolicy",
                "summary": "Disclose the grading policy in use",
                "responses": {"200": {"description": "Policy", "content": {"application/json": {"schema": {"$ref": "#/components/schemas/GradingPolicy"}}}}},
            }
        },
    }
    if spec.persistence_required:
        paths["/api/v1/gpa/calculations"]["get"] = {
            "operationId": "listGpaCalculations",
            "summary": "List previous calculations, newest first",
            "responses": {"200": {"description": "History", "content": {"application/json": {"schema": {
                "type": "object", "required": ["items"],
                "properties": {"items": {"type": "array", "items": {"$ref": "#/components/schemas/GpaCalculation"}}}}}}}},
        }
    if spec.clear_history:
        paths["/api/v1/gpa/calculations"]["delete"] = {
            "operationId": "clearGpaHistory",
            "summary": "Delete every stored calculation",
            "responses": {"204": {"description": "History cleared"}},
        }
    document = {
        "openapi": "3.1.0",
        "info": {"title": "GPA Calculator API", "version": "1.0.0", "description": "Generated by InteliSE Component 3 from released C2 design and approved C1 requirements."},
        "paths": paths,
        "components": {
            "schemas": {
                "ModuleResult": {"type": "object", "required": ["moduleCode", "credits", "grade"], "properties": module_props},
                "GpaCalculationRequest": {"type": "object", "required": ["modules"], "properties": {"modules": {
                    "type": "array", "minItems": 1, "maxItems": spec.max_modules, "items": {"$ref": "#/components/schemas/ModuleResult"}}}},
                "GpaCalculation": {"type": "object", "required": ["id", "gpa", "totalCredits", "policyId", "policyVersion", "modules"], "properties": calc_props},
                "GradingPolicy": {"type": "object", "properties": {
                    "policyId": {"type": "string"}, "policyVersion": {"type": "string"}, "authorityStatus": {"type": "string"},
                    "grades": {"type": "array", "items": {"type": "object", "properties": {"grade": {"type": "string"}, "gradePoint": {"type": "number"}}}}}},
                "ErrorResponse": {"type": "object", "required": ["error"], "properties": {"error": {"type": "object", "required": ["code", "status", "message"], "properties": {
                    "code": {"type": "string"}, "status": {"type": "string", "enum": ["INVALID_INPUT", "REVIEW_REQUIRED", "NOT_FOUND", "INTERNAL"]},
                    "message": {"type": "string"}, "details": {"type": "array", "items": {"type": "object"}}}}}},
            }
        },
    }
    return {"openapi/openapi.json": _json(document) + "\n"}


# --------------------------------------------------------------------------- frontend


def render_frontend_shell(spec: GpaSpec, *, policy_banner: bool = False) -> dict[str, str]:
    """``policy_banner`` is only True for the UI-gate control (render_frontend_ui), whose required cases check the banner."""
    package = {
        "name": "gpa-calculator-frontend",
        "private": True,
        "version": "1.0.0",
        "type": "module",
        "engines": {"node": ">=24 <25"},
        "scripts": {"build": "vite build", "dev": "vite --host 127.0.0.1"},
        "dependencies": {"react": "18.3.1", "react-dom": "18.3.1"},
        "devDependencies": {"vite": "8.3.4", "@vitejs/plugin-react": "5.2.0"},
    }
    index_html = """
<!doctype html>
<html lang="en">
  <head>
    <meta charset="UTF-8" />
    <meta name="viewport" content="width=device-width, initial-scale=1.0" />
    <title>GPA Calculator</title>
    <link rel="icon" href="data:," />
  </head>
  <body>
    <div id="root"></div>
    <script type="module" src="/src/main.jsx"></script>
  </body>
</html>
"""
    vite = """
import { defineConfig } from 'vite';
import react from '@vitejs/plugin-react';

export default defineConfig({ plugins: [react()] });
"""
    main = """
import React from 'react';
import { createRoot } from 'react-dom/client';
import { App } from './App.jsx';
import './styles.css';

createRoot(document.getElementById('root')).render(
  <React.StrictMode>
    <App />
  </React.StrictMode>,
);
"""
    app = """
__REACT_IMPORT__
import { GpaCalculatorForm } from './components/GpaCalculatorForm.jsx';
import { GpaResult } from './components/GpaResult.jsx';
__POLICY_IMPORT__
__HISTORY_IMPORT__

export function App() {
  const [result, setResult] = useState(null);
__HISTORY_STATE__

  return (
    <main className="page">
      <header className="hero">
        <h1>GPA Calculator</h1>
        <p>Enter your module results to calculate a credit-weighted GPA.</p>
      </header>
__POLICY_VIEW__
      <div className="layout">
        <GpaCalculatorForm onCalculated={(calculation) => { setResult(calculation); __REFRESH__ }} />
        <aside className="side">
          <GpaResult result={result} />
__HISTORY_VIEW__
        </aside>
      </div>
    </main>
  );
}
"""
    history = spec.persistence_required
    api = """
// API client for the generated backend. Errors keep the server's field-level details.
const BASE_URL = (import.meta.env.VITE_API_BASE_URL || 'http://127.0.0.1:3001').replace(/\\/$/, '');

export class ApiError extends Error {
  constructor(message, status, code, details) {
    super(message);
    this.status = status;
    this.code = code;
    this.details = details || [];
  }
}

async function request(path, options = {}) {
  let response;
  try {
    response = await fetch(`${BASE_URL}${path}`, { headers: { 'Content-Type': 'application/json' }, ...options });
  } catch {
    throw new ApiError('The GPA service is unreachable.', 0, 'NETWORK_ERROR');
  }
  const body = await response.json().catch(() => null);
  if (!response.ok) {
    const error = body && body.error ? body.error : {};
    throw new ApiError(error.message || `Request failed with HTTP ${response.status}.`, response.status, error.code, error.details);
  }
  return body;
}

export function calculateGpa(modules) {
  return request('/api/v1/gpa/calculations', { method: 'POST', body: JSON.stringify({ modules }) });
}

export async function listCalculations() {
  const body = await request('/api/v1/gpa/calculations');
  return body.items;
}
"""
    styles = """
:root {
  --bg: #f3f5f9; --surface: #ffffff; --ink: #172033; --muted: #5b6577; --line: #dde3ec;
  --brand: #2f7a63; --brand-ink: #ffffff; --brand-soft: #e7f2ee; --danger: #b42318; --danger-soft: #fdecea;
  --warn: #8a5300; --warn-soft: #fff4e0; --ok: #136c3a; --radius: 14px;
  font-family: "Inter", "Segoe UI", system-ui, -apple-system, sans-serif; color: var(--ink); background: var(--bg);
  line-height: 1.45;
}
* { box-sizing: border-box; }
body { margin: 0; }
.page { max-width: 1120px; margin: 0 auto; padding: 0 16px 56px; }
.hero { color: var(--ink); border-bottom: 1px solid var(--line); padding: 26px 24px 18px; margin: 0 -16px 20px; }
.hero h1 { margin: 0; font-size: clamp(24px, 4vw, 32px); letter-spacing: -0.02em; }
.hero p { margin: 6px 0 0; color: var(--muted); }
.layout { display: grid; gap: 18px; grid-template-columns: minmax(0, 1fr); }
@media (min-width: 900px) { .layout { grid-template-columns: minmax(0, 1.8fr) minmax(280px, 1fr); align-items: start; } }
.side { display: grid; gap: 18px; align-content: start; min-width: 0; }
.card { background: var(--surface); border: 1px solid var(--line); border-radius: var(--radius); padding: 20px; box-shadow: 0 1px 2px rgba(23, 32, 51, 0.05); }
.card h2 { margin: 0 0 14px; font-size: 18px; }
.policy { border: 1px solid #f1d29b; background: var(--warn-soft); color: var(--warn); border-radius: 10px; padding: 10px 14px; font-size: 14px; margin: 0 0 18px; }
table { width: 100%; border-collapse: separate; border-spacing: 0 8px; }
th { text-align: left; font-size: 12px; text-transform: uppercase; letter-spacing: 0.04em; color: var(--muted); padding: 0 6px; }
td { padding: 0 6px; vertical-align: top; }
input, select { width: 100%; padding: 10px 12px; border: 1px solid #c3cad6; border-radius: 10px; font: inherit; background: #fff; color: var(--ink); }
input:focus, select:focus, button:focus-visible { outline: 3px solid #9ccdbd; outline-offset: 1px; border-color: var(--brand); }
input[type='checkbox'] { width: 20px; height: 20px; margin-top: 10px; accent-color: var(--brand); }
input[aria-invalid='true'], select[aria-invalid='true'] { border-color: var(--danger); background: var(--danger-soft); }
.field-error { display: block; color: var(--danger); font-size: 12.5px; margin-top: 4px; }
.form-error { color: var(--danger); background: var(--danger-soft); border-radius: 10px; padding: 10px 12px; margin: 14px 0 0; }
.actions { display: flex; gap: 10px; margin-top: 14px; flex-wrap: wrap; }
button { padding: 10px 16px; border-radius: 10px; border: 1px solid var(--brand); background: var(--brand); color: var(--brand-ink); font: inherit; font-weight: 600; cursor: pointer; }
button.secondary { background: #fff; color: var(--brand); }
button.icon { padding: 8px 12px; border-color: var(--line); color: var(--muted); background: #fff; font-weight: 500; }
button.icon:disabled { background: #eef1f4; border-color: #e3e8ee; color: #9aa4b2; opacity: 1; }
button:disabled { opacity: 0.55; cursor: not-allowed; }
.result { text-align: center; }
.result h2 { text-align: left; }
.gpa { font-size: clamp(44px, 9vw, 64px); font-weight: 800; letter-spacing: -0.03em; color: var(--brand); margin: 4px 0; }
.result dl { display: grid; grid-template-columns: max-content minmax(0, 1fr); gap: 6px 12px; text-align: left; font-size: 14px; color: var(--muted); margin: 12px 0 0; }
.result dd { margin: 0; color: var(--ink); font-weight: 600; overflow-wrap: anywhere; }
select { min-width: 104px; }
.empty { color: var(--muted); font-size: 14px; background: #f3f5f8; border-radius: 10px; padding: 18px 14px; text-align: center; margin: 0; }
::placeholder { color: #98a2b3; }
.history { list-style: none; padding: 0; margin: 0; display: grid; gap: 8px; }
.history li { display: flex; justify-content: space-between; gap: 12px; border: 1px solid var(--line); border-radius: 10px; padding: 10px 12px; font-size: 14px; }
.history strong { color: var(--brand); }
.confirm p { margin: 14px 0 0; font-weight: 600; }
.visually-hidden { position: absolute; width: 1px; height: 1px; overflow: hidden; clip: rect(0 0 0 0); white-space: nowrap; }
@media (max-width: 640px) {
  thead { display: none; }
  table, tbody, tr, td { display: block; width: 100%; }
  tr { border: 1px solid var(--line); border-radius: 12px; padding: 12px 10px 4px; margin-bottom: 10px; }
  td { padding: 0 0 10px; }
  td[data-label]::before { content: attr(data-label); display: block; font-size: 12px; color: var(--muted); margin-bottom: 4px; }
  .actions button { flex: 1 1 auto; }
}
"""
    files = {
        "frontend/package.json": _json(package) + "\n",
        "frontend/index.html": _fill(index_html),
        "frontend/vite.config.js": _fill(vite),
        "frontend/src/main.jsx": _fill(main),
        "frontend/src/App.jsx": _fill(
            app,
            REACT_IMPORT=(
                "import { useCallback, useEffect, useState } from 'react';" if history else "import { useState } from 'react';"
            ),
            HISTORY_IMPORT=(
                "import { HistoryList } from './components/HistoryList.jsx';\n"
                + (
                    "import { clearCalculations, listCalculations } from './api/gpaApi.js';"
                    if spec.clear_history
                    else "import { listCalculations } from './api/gpaApi.js';"
                )
            ) if history else "",
            HISTORY_STATE=(
                "  const [history, setHistory] = useState([]);\n"
                "  const [historyError, setHistoryError] = useState(null);\n"
                "  const refresh = useCallback(() => {\n"
                "    listCalculations().then((items) => { setHistory(items); setHistoryError(null); }).catch((error) => setHistoryError(error.message));\n"
                "  }, []);\n"
                "  useEffect(() => { refresh(); }, [refresh]);"
                + (
                    "\n  const clear = useCallback(() => {\n"
                    "    clearCalculations().then(refresh).catch((error) => setHistoryError(error.message));\n"
                    "  }, [refresh]);"
                    if spec.clear_history
                    else ""
                )
            ) if history else "",
            REFRESH="refresh();" if history else "",
            POLICY_IMPORT="import { PolicyDisclosure } from './components/PolicyDisclosure.jsx';" if policy_banner else "",
            POLICY_VIEW="      <PolicyDisclosure />" if policy_banner else "",
            HISTORY_VIEW=(
                "      <HistoryList items={history} error={historyError}" + (" onClear={clear}" if spec.clear_history else "") + " />"
            ) if history else "",
        ),
        "frontend/src/styles.css": styles.strip("\n") + "\n",
        "frontend/src/api/gpaApi.js": _fill(api) + (
            "\nexport function clearCalculations() {\n  return request('/api/v1/gpa/calculations', { method: 'DELETE' });\n}\n"
            if spec.clear_history
            else ""
        ),
    }
    if spec.llm_frontend:
        # The LLM writes these two; everything else here (package pins, index.html, vite config, main.jsx, API client)
        # is trusted scaffold because it controls dependencies and is the only module allowed to use the network.
        files.pop("frontend/src/App.jsx")
        files.pop("frontend/src/styles.css")
    return files


def render_frontend_ui(spec: GpaSpec) -> dict[str, str]:
    """Template equivalents of the files an LLM writes in LLM-frontend mode (control experiment and reference)."""
    base = replace(spec, llm_frontend=False)
    shell = render_frontend_shell(base, policy_banner=True)
    files = {path: shell[path] for path in ("frontend/src/App.jsx", "frontend/src/styles.css")}
    files.update(render_frontend_form(base))
    files.update(render_frontend_validation(base))
    return files


def seam_module_id(spec: GpaSpec, seam: "TestSeam") -> str:
    """The UI form seam lives in fe.ui when an LLM writes the UI (fe.gpa-form and fe.validation are merged into it)."""
    return "fe.ui" if spec.llm_frontend and seam.module_id == "fe.gpa-form" else seam.module_id


def render_frontend_policy(spec: GpaSpec) -> dict[str, str]:
    template = """
// Generated from KB-GPA-GRADE-SCALE for display and client-side validation only.
export const POLICY = Object.freeze(__POLICY__);

export const GRADE_OPTIONS = Object.freeze(__OPTIONS__);
"""
    options = [{"grade": entry.grade, "gradePoint": entry.grade_point} for entry in spec.policy.grades]
    return {
        "frontend/src/policy/gradingPolicy.js": _fill(template, POLICY=_json(_policy_payload(spec)), OPTIONS=_json(options))
    }


def render_frontend_validation(spec: GpaSpec) -> dict[str, str]:
    template = """
// Client-side mirror of the backend validator. The backend remains authoritative.
import { GRADE_OPTIONS } from '../policy/gradingPolicy.js';

export const CONSTRAINTS = Object.freeze(__CONSTRAINTS__);

const CODE_PATTERN = CONSTRAINTS.moduleCode.pattern ? new RegExp(CONSTRAINTS.moduleCode.pattern) : null;
const GRADES = new Set(GRADE_OPTIONS.map((option) => option.grade));

export function validateRows(rows) {
  const errors = {};
  const formErrors = [];
  const modules = [];
  const seen = new Set();
  const add = (rowId, field, message) => {
    errors[rowId] = { ...(errors[rowId] || {}), [field]: message };
  };
  if (rows.length === 0) formErrors.push('Add at least one module.');
  if (rows.length > CONSTRAINTS.maxModules) formErrors.push(`At most ${CONSTRAINTS.maxModules} modules are accepted.`);
  for (const row of rows) {
    const moduleCode = row.moduleCode.trim();
    const credits = row.credits === '' ? NaN : Number(row.credits);
    if (CONSTRAINTS.moduleCode.required && !moduleCode) add(row.rowId, 'moduleCode', 'Module code is required.');
    else if (CONSTRAINTS.moduleCode.maxLength && moduleCode.length > CONSTRAINTS.moduleCode.maxLength) add(row.rowId, 'moduleCode', 'Module code is too long.');
    else if (CODE_PATTERN && !CODE_PATTERN.test(moduleCode)) add(row.rowId, 'moduleCode', `Module code must match ${CONSTRAINTS.moduleCode.pattern}.`);
    if (credits === 0) add(row.rowId, 'credits', 'A module counted toward GPA cannot have zero credits.');
    else if (!Number.isInteger(credits) || credits < CONSTRAINTS.credits.min || credits > CONSTRAINTS.credits.max) add(row.rowId, 'credits', `Enter a whole number from ${CONSTRAINTS.credits.min} to ${CONSTRAINTS.credits.max}.`);
    if (!row.grade) add(row.rowId, 'grade', 'Choose a grade.');
    else if (!GRADES.has(row.grade)) add(row.rowId, 'grade', 'This grade is not in the accepted policy.');
    if (moduleCode) {
      if (seen.has(moduleCode.toUpperCase())) add(row.rowId, 'moduleCode', 'This module is repeated; the policy does not define repeats, so it needs review.');
      seen.add(moduleCode.toUpperCase());
    }
    modules.push({ moduleCode, credits, grade: row.grade, countsTowardGpa: row.countsTowardGpa });
  }
  return { errors, formErrors, modules };
}
"""
    return {"frontend/src/validation/moduleValidation.js": _fill(template, CONSTRAINTS=_json(constraint_payload(spec)))}


def render_frontend_form(spec: GpaSpec) -> dict[str, str]:
    form = """
import { useState } from 'react';
import { ModuleRow } from './ModuleRow.jsx';
import { validateRows } from '../validation/moduleValidation.js';
import { calculateGpa } from '../api/gpaApi.js';

let nextRowId = 1;
function newRow() {
  const rowId = `row-${nextRowId}`;
  nextRowId += 1;
  return { rowId, moduleCode: '', credits: '', grade: '', countsTowardGpa: true };
}

export function GpaCalculatorForm({ onCalculated }) {
  const [rows, setRows] = useState(() => [newRow()]);
  const [fieldErrors, setFieldErrors] = useState({});
  const [formError, setFormError] = useState(null);
  const [submitting, setSubmitting] = useState(false);

  const updateRow = (rowId, field, value) => setRows((current) => current.map((row) => (row.rowId === rowId ? { ...row, [field]: value } : row)));
  const removeRow = (rowId) => setRows((current) => (current.length > 1 ? current.filter((row) => row.rowId !== rowId) : current));

  async function submit(event) {
    event.preventDefault();
    const { errors, formErrors, modules } = validateRows(rows);
    setFieldErrors(errors);
    setFormError(formErrors[0] || (Object.keys(errors).length ? 'Fix the highlighted fields.' : null));
    if (formErrors.length || Object.keys(errors).length) return;
    setSubmitting(true);
    try {
      onCalculated(await calculateGpa(modules));
    } catch (error) {
      const serverErrors = {};
      for (const detail of error.details || []) {
        const row = Number.isInteger(detail.index) ? rows[detail.index] : null;
        if (row && detail.field) serverErrors[row.rowId] = { ...(serverErrors[row.rowId] || {}), [detail.field]: detail.message || error.message };
      }
      setFieldErrors(serverErrors);
      setFormError(error.status === 422 ? `Review required: ${error.message}` : error.message);
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <form className="card" onSubmit={submit} noValidate aria-labelledby="gpa-form-title" data-testid="gpa-form">
      <h2 id="gpa-form-title">Module results</h2>
      <table>
        <thead>
          <tr><th scope="col">Module code</th><th scope="col">Credits</th><th scope="col">Grade</th><th scope="col">Counts toward GPA</th><th scope="col"><span className="visually-hidden">Actions</span></th></tr>
        </thead>
        <tbody>
          {rows.map((row, index) => (
            <ModuleRow key={row.rowId} row={row} position={index + 1} errors={fieldErrors[row.rowId] || {}} onChange={updateRow} onRemove={removeRow} canRemove={rows.length > 1} />
          ))}
        </tbody>
      </table>
      <div className="actions">
        <button type="button" className="secondary" onClick={() => setRows((current) => [...current, newRow()])} data-testid="add-module">Add module</button>
        <button type="submit" disabled={submitting} data-testid="calculate-gpa">{submitting ? 'Calculating...' : 'Calculate GPA'}</button>
      </div>
      {formError && <p className="form-error" role="alert" data-testid="form-error">{formError}</p>}
    </form>
  );
}
"""
    row = """
import { GRADE_OPTIONS } from '../policy/gradingPolicy.js';

export function ModuleRow({ row, position, errors, onChange, onRemove, canRemove }) {
  const id = (field) => `${row.rowId}-${field}`;
  const describedBy = (field) => (errors[field] ? `${id(field)}-error` : undefined);
  return (
    <tr data-testid="module-row">
      <td data-label="Module code">
        <label className="visually-hidden" htmlFor={id('moduleCode')}>Module code (row {position})</label>
        <input id={id('moduleCode')} value={row.moduleCode} onChange={(event) => onChange(row.rowId, 'moduleCode', event.target.value)} aria-invalid={Boolean(errors.moduleCode)} aria-describedby={describedBy('moduleCode')} placeholder="e.g. IT1010" data-testid="module-code" />
        {errors.moduleCode && <span id={`${id('moduleCode')}-error`} className="field-error">{errors.moduleCode}</span>}
      </td>
      <td data-label="Credits">
        <label className="visually-hidden" htmlFor={id('credits')}>Credits (row {position})</label>
        <input id={id('credits')} type="number" inputMode="numeric" min="0" step="1" value={row.credits} onChange={(event) => onChange(row.rowId, 'credits', event.target.value)} aria-invalid={Boolean(errors.credits)} aria-describedby={describedBy('credits')} placeholder="e.g. 4" data-testid="module-credits" />
        {errors.credits && <span id={`${id('credits')}-error`} className="field-error">{errors.credits}</span>}
      </td>
      <td data-label="Grade">
        <label className="visually-hidden" htmlFor={id('grade')}>Grade (row {position})</label>
        <select id={id('grade')} value={row.grade} onChange={(event) => onChange(row.rowId, 'grade', event.target.value)} aria-invalid={Boolean(errors.grade)} aria-describedby={describedBy('grade')} data-testid="module-grade">
          <option value="">Choose…</option>
          {GRADE_OPTIONS.map((option) => <option key={option.grade} value={option.grade}>{option.grade} ({option.gradePoint.toFixed(1)})</option>)}
        </select>
        {errors.grade && <span id={`${id('grade')}-error`} className="field-error">{errors.grade}</span>}
      </td>
      <td data-label="Counts toward GPA">
        <label>
          <input type="checkbox" checked={row.countsTowardGpa} onChange={(event) => onChange(row.rowId, 'countsTowardGpa', event.target.checked)} data-testid="module-counts" />
          <span className="visually-hidden">Counts toward GPA (row {position})</span>
        </label>
      </td>
      <td>
        <button type="button" className="icon" onClick={() => onRemove(row.rowId)} disabled={!canRemove} aria-label={`Remove row ${position}`} data-testid="remove-module">Remove</button>
      </td>
    </tr>
  );
}
"""
    result = """
export function GpaResult({ result }) {
  return (
    <section className="card result" aria-live="polite" data-testid="gpa-result">
      <h2>GPA result</h2>
      {!result && <p className="empty">Your GPA appears here after you calculate.</p>}
      {result && (
        <>
          <p className="gpa" data-testid="gpa-value">{result.gpaText}</p>
          <dl>
            <dt>GPA credits</dt><dd>{result.totalCredits}</dd>
            <dt>Weighted points</dt><dd>{result.weightedGradePoints}</dd>
            <dt>Policy</dt><dd>{result.policyId} v{result.policyVersion}</dd>
            <dt>Authority</dt><dd>{result.policyAuthorityStatus}</dd>
          </dl>
        </>
      )}
    </section>
  );
}
"""
    disclosure = """
import { POLICY } from '../policy/gradingPolicy.js';

export function PolicyDisclosure() {
  const sample = POLICY.authorityStatus === 'SAMPLE_RESEARCH_POLICY';
  return (
    <p className="policy" role="note" data-testid="policy-disclosure">
      Grading policy <strong>{POLICY.policyId}</strong> v{POLICY.policyVersion} - {POLICY.authorityStatus}.
      {sample && ' This is a research transcription of a publicly described scale, not an official institutional calculation.'}
      {' '}Rounding: {POLICY.rounding.decimalPlaces} decimal places, {POLICY.rounding.mode}.
    </p>
  );
}
"""
    history = """
export function HistoryList({ items, error }) {
  return (
    <section className="card" data-testid="gpa-history">
      <h2>Calculation history</h2>
      {error && <p className="form-error" role="alert">History unavailable: {error}</p>}
      {!error && items.length === 0 && <p className="empty">No calculations yet.</p>}
      <ul className="history">
        {items.map((item) => (
          <li key={item.id}>
            <span>{new Date(item.createdAt).toLocaleString()} – {item.totalCredits} credits</span>
            <strong>{item.gpaText}</strong>
          </li>
        ))}
      </ul>
    </section>
  );
}
"""
    history_with_clear = """
import { useState } from 'react';

export function HistoryList({ items, error, onClear }) {
  const [confirming, setConfirming] = useState(false);
  return (
    <section className="card" data-testid="gpa-history">
      <h2>Calculation history</h2>
      {error && <p className="form-error" role="alert">History unavailable: {error}</p>}
      {!error && items.length === 0 && <p className="empty">No calculations yet.</p>}
      <ul className="history">
        {items.map((item) => (
          <li key={item.id}>
            <span>{new Date(item.createdAt).toLocaleString()} – {item.totalCredits} credits</span>
            <strong>{item.gpaText}</strong>
          </li>
        ))}
      </ul>
      {items.length > 0 && !confirming && (
        <div className="actions">
          <button type="button" className="secondary" data-testid="gpa-history-clear" onClick={() => setConfirming(true)}>Clear history</button>
        </div>
      )}
      {confirming && (
        <div className="confirm" role="alert">
          <p>Delete all {items.length} calculations?</p>
          <div className="actions">
            <button type="button" data-testid="gpa-history-clear-confirm" onClick={() => { setConfirming(false); onClear(); }}>Yes, delete</button>
            <button type="button" className="secondary" onClick={() => setConfirming(false)}>Cancel</button>
          </div>
        </div>
      )}
    </section>
  );
}
"""
    files = {
        "frontend/src/components/GpaCalculatorForm.jsx": _fill(form),
        "frontend/src/components/ModuleRow.jsx": _fill(row),
        "frontend/src/components/GpaResult.jsx": _fill(result),
        "frontend/src/components/PolicyDisclosure.jsx": _fill(disclosure),
    }
    if spec.persistence_required:
        files["frontend/src/components/HistoryList.jsx"] = _fill(history_with_clear if spec.clear_history else history)
    return files


# --------------------------------------------------------------------------- seams, deployment, docs


def render_test_seams(spec: GpaSpec) -> dict[str, str]:
    seams = [
        {
            "seam_id": seam.seam_id,
            "seam_type": seam.seam_type,
            "module_id": seam_module_id(spec, seam),
            "uml_classes": list(seam.classes()),
            "reference": seam.reference,
            "usage": seam.description.replace("save(calculation) and list()", "save(calculation), list() and clear()")
            if spec.clear_history
            else seam.description,
        }
        for seam in TEST_SEAMS
        if seam_applies(seam, spec.persistence_required, spec.clear_history)
    ]
    document = {
        "schema": "C3_TEST_SEAMS_V1",
        "ownership": "Component 3 publishes seams only. Component 4 owns independent tests, defect truth and readiness.",
        "seams": seams,
        "operations": [{"operation_id": op.operation_id, "method": op.method, "path": op.path} for op in _operations(spec)],
        "digest_note": "Exact module and artifact digests are in generation-manifest.json; C4 must cite them in defect and readiness reports.",
    }
    readme = """
# Test seams for Component 4

Component 3 publishes these seams so Component 4 can test the generated GPA application
independently. `backend/test/gpa.smoke.test.js` is a C3-owned smoke check run during the
Docker build; it is **not** Component 4 evidence.

* `c4-test-seams.json` lists every seam, its module and the operation IDs.
* Cite `generation_run_id`, `artifact_digest_sha256` and the module digest from
  `generation-manifest.json` in every defect report or readiness signal; C3 rejects stale digests.
"""
    return {"test-seams/c4-test-seams.json": _json(document) + "\n", "test-seams/README.md": _fill(readme)}


def render_deployment(_spec: GpaSpec) -> dict[str, str]:
    backend = """
# Disposable preview image for the generated backend. Non-root, no secrets baked in.
FROM node:24-bookworm-slim AS build
WORKDIR /app/backend
COPY backend/package.json ./
RUN npm install --ignore-scripts --no-audit --no-fund
COPY backend/ ./
COPY database/ /app/database/
RUN npm test

FROM node:24-bookworm-slim
ENV NODE_ENV=production HOST=0.0.0.0 PORT=3001
WORKDIR /app
COPY --from=build --chown=node:node /app/backend /app/backend
COPY --from=build --chown=node:node /app/database /app/database
USER node
EXPOSE 3001
HEALTHCHECK --interval=3s --timeout=3s --retries=40 CMD ["node", "-e", "fetch('http://127.0.0.1:3001/api/health').then((r) => process.exit(r.ok ? 0 : 1)).catch(() => process.exit(1))"]
CMD ["node", "backend/src/server.js"]
"""
    frontend = """
# Disposable preview image for the generated frontend. Built bundle served by a static server as a non-root user.
FROM node:24-bookworm-slim AS build
WORKDIR /app/frontend
COPY frontend/package.json ./
RUN npm install --ignore-scripts --no-audit --no-fund
COPY frontend/ ./
ARG VITE_API_BASE_URL
ENV VITE_API_BASE_URL=$VITE_API_BASE_URL
RUN npm run build

FROM node:24-bookworm-slim
WORKDIR /app
COPY --from=build --chown=node:node /app/frontend/dist /app/dist
COPY --chown=node:node deployment/static-server.mjs /app/static-server.mjs
USER node
EXPOSE 8080
HEALTHCHECK --interval=3s --timeout=3s --retries=20 CMD ["node", "-e", "fetch('http://127.0.0.1:8080/').then((r) => process.exit(r.ok ? 0 : 1)).catch(() => process.exit(1))"]
CMD ["node", "/app/static-server.mjs"]
"""
    server = """
// Minimal static server for the built frontend (no directory listing, no path traversal).
import { createServer } from 'node:http';
import { readFile } from 'node:fs/promises';
import path from 'node:path';

const root = path.resolve('/app/dist');
const types = { '.html': 'text/html; charset=utf-8', '.js': 'text/javascript', '.css': 'text/css', '.svg': 'image/svg+xml', '.json': 'application/json' };

createServer(async (req, res) => {
  const url = new URL(req.url, 'http://localhost');
  let target = path.resolve(root, '.' + decodeURIComponent(url.pathname));
  if (!target.startsWith(root)) {
    res.writeHead(403).end();
    return;
  }
  if (url.pathname === '/' || !path.extname(target)) target = path.join(root, 'index.html');
  try {
    const body = await readFile(target);
    res.writeHead(200, { 'Content-Type': types[path.extname(target)] || 'application/octet-stream', 'X-Content-Type-Options': 'nosniff' });
    res.end(body);
  } catch {
    res.writeHead(404).end();
  }
}).listen(8080, '0.0.0.0');
"""
    plan = {
        "schema": "C3_PREVIEW_PLAN_V1",
        "note": "Descriptive only. The C3 preview orchestrator enforces these controls itself and does not trust this file.",
        "services": [
            {"name": "database", "image": "postgres:16-alpine", "published": False, "user": "70:70", "storage": "tmpfs"},
            {"name": "backend", "dockerfile": "deployment/backend.Dockerfile", "container_port": 3001, "published": "127.0.0.1 only", "user": "node"},
            {"name": "frontend", "dockerfile": "deployment/frontend.Dockerfile", "container_port": 8080, "published": "127.0.0.1 only", "user": "node"},
        ],
        "controls": [
            "non-root users", "loopback-only published ports", "no Docker socket mount", "no privileged mode",
            "no host-source bind mounts", "cap-drop ALL", "no-new-privileges", "memory/cpu/pids limits",
            "ephemeral per-preview database credentials", "URLs reported only after health checks pass",
        ],
    }
    return {
        "deployment/backend.Dockerfile": _fill(backend),
        "deployment/frontend.Dockerfile": _fill(frontend),
        "deployment/static-server.mjs": _fill(server),
        "deployment/preview-plan.json": _json(plan) + "\n",
    }


def render_docs(spec: GpaSpec) -> dict[str, str]:
    readme = f"""
# Generated GPA Calculator

Generated by InteliSE Component 3 ({TEMPLATE_SET_REF}) from approved C1 requirements, the
released C2 design and the accepted Knowledge Base grading policy `{spec.policy.policy_id}`.

> Policy authority: **{spec.policy.authority_status}**. {spec.policy.authority_status_reason}

| Folder | Contents |
| --- | --- |
| `frontend/` | React GPA entry form, validation mirror, policy disclosure |
| `backend/` | Express routes -> controllers -> services -> repositories -> PostgreSQL |
| `database/` | Forward-only PostgreSQL migrations |
| `openapi/` | OpenAPI 3.1 contract with stable operation IDs |
| `test-seams/` | Seams for Component 4 (C3 does not own C4 tests) |
| `deployment/` | Disposable Docker preview definitions |
| `traceability/` | Living-traceability export for this run |

Exact upstream versions, rule IDs, digests and the generation run ID are recorded in
`generation-manifest.json`, not in source files, so unchanged modules keep identical hashes.
"""
    return {"README.md": readme.strip("\n") + "\n"}


MODULES: dict[str, ModuleTemplate] = {
    module.module_id: module
    for module in (
        ModuleTemplate("fe.app-shell", "FRONTEND", "FRONTEND", "tpl.react.app-shell", (), render_frontend_shell, "react", "ui"),
        ModuleTemplate("fe.gpa-form", "FRONTEND", "FRONTEND", "tpl.react.gpa-form", ("ModuleResult", "GpaCalculation"), render_frontend_form, "react", "ui"),
        ModuleTemplate("fe.validation", "FRONTEND", "FRONTEND", "tpl.react.validation", ("ModuleResult",), render_frontend_validation, "react", "ui"),
        ModuleTemplate("fe.policy", "FRONTEND", "FRONTEND", "tpl.react.policy", ("GradingPolicy",), render_frontend_policy, "react", "ui"),
        ModuleTemplate("fe.ui", "FRONTEND", "FRONTEND", "tpl.react.ui", ("ModuleResult", "GpaCalculation"), render_frontend_ui, "react", "ui"),
        ModuleTemplate("be.app", "COMPOSITION_ROOT", "COMPOSITION_ROOT", "tpl.node.app", (), render_backend_app, "node", "controller"),
        ModuleTemplate("be.routes", "ROUTE", "API", "tpl.node.routes", ("GpaCalculationService",), render_backend_routes, "node", "api"),
        ModuleTemplate("be.controller", "CONTROLLER", "CONTROLLER", "tpl.node.controller", ("GpaCalculationService",), render_backend_controller, "node", "controller"),
        ModuleTemplate("be.service", "SERVICE", "BUSINESS_LOGIC", "tpl.node.gpa-service", ("GpaCalculationService",), render_backend_service, "node", "service"),
        ModuleTemplate("be.policy", "POLICY", "BUSINESS_LOGIC", "tpl.node.grading-policy", ("GradingPolicy",), render_backend_policy, "node", "service"),
        ModuleTemplate("be.validation", "VALIDATION", "VALIDATION", "tpl.node.validation", ("ModuleResult",), render_backend_validation, "node", "api"),
        ModuleTemplate("be.repository", "REPOSITORY", "REPOSITORY", "tpl.node.repository", ("GpaCalculationRepository",), render_backend_repository, "node", "repository"),
        ModuleTemplate("be.smoke", "TEST", "TEST", "tpl.node.smoke", (), render_backend_smoke, "node", "service"),
        ModuleTemplate("db.schema", "DATABASE", "DATABASE", "tpl.postgres.migration", ("GpaCalculation", "ModuleResult"), render_database, "node", "database"),
        ModuleTemplate("api.openapi", "API", "API", "tpl.openapi.contract", ("GpaCalculation", "ModuleResult"), render_openapi, "node", "api"),
        ModuleTemplate("test-seams", "TEST_SEAM", "TEST_SEAM", "tpl.test-seams", (), render_test_seams, "node", "test_seam"),
        ModuleTemplate("deployment", "DEPLOYMENT", "DEPLOYMENT", "tpl.docker.preview", (), render_deployment, "node", "deployment"),
        ModuleTemplate("docs", "DOCUMENTATION", "DOCUMENTATION", "tpl.docs.readme", (), render_docs, "node", "api"),
    )
}


def render_modules(spec: GpaSpec, module_ids: list[str] | tuple[str, ...]) -> dict[str, dict[str, str]]:
    """Render the requested modules; returns {module_id: {path: content}}."""
    rendered: dict[str, dict[str, str]] = {}
    for module_id in sorted(set(module_ids)):
        template = MODULES[module_id]
        rendered[module_id] = {path: content for path, content in sorted(template.render(spec).items())}
    return rendered
