"""Deterministic React + Express renderers for the Stage 1 CRUD profile."""

from __future__ import annotations

from dataclasses import dataclass
import json
import re

from intelise_c3.domain.crud_spec import (
    CrudApplicationSpec,
    CrudEntitySpec,
    CrudFieldSpec,
    CrudScalarType,
)
from intelise_c3.domain.generation import (
    ApiArtifactReference,
    ApiOperationIdentity,
    DatabaseArtifactReference,
    DatabaseColumnIdentity,
    DatabaseTableIdentity,
    GeneratedArtifactType,
    GenerationManifest,
    TestSeamReference,
)
from intelise_c3.generation.templates import TemplateArtifact

DYNAMIC_GENERATOR_VERSION = "react-node-crud-generator-v1"
DYNAMIC_TEMPLATE_SET_VERSION = "react-node-crud-scaffold-v1"
DYNAMIC_TRACEABILITY_MAPPING_POLICY_VERSION = "crud-spec-traceability-v1"


def is_dynamic_crud_manifest(manifest: GenerationManifest) -> bool:
    evidence = manifest.run_evidence
    return (
        evidence.generator_version == DYNAMIC_GENERATOR_VERSION
        or evidence.template_set_version == DYNAMIC_TEMPLATE_SET_VERSION
    )


@dataclass(frozen=True)
class CrudRenderResult:
    artifacts: tuple[TemplateArtifact, ...]
    api_references: tuple[ApiArtifactReference, ...]
    database_references: tuple[DatabaseArtifactReference, ...]
    test_seams: tuple[TestSeamReference, ...]


def render_crud_application(spec: CrudApplicationSpec) -> CrudRenderResult:
    """Render one complete deterministic project without writing or executing it."""
    api_references = _api_references(spec)
    database_references = _database_references(spec)
    test_seams = _test_seams(spec)
    artifacts: list[TemplateArtifact] = [
        _plain("README.md", "generated-project-readme", GeneratedArtifactType.DOCUMENTATION, _readme(spec)),
        _plain("frontend/package.json", "frontend-package", GeneratedArtifactType.CONFIGURATION, _frontend_package(spec)),
        _plain("frontend/vite.config.js", "frontend-build-configuration", GeneratedArtifactType.CONFIGURATION, _vite_config()),
        _plain("frontend/index.html", "frontend-entry-document", GeneratedArtifactType.FRONTEND, _index_html(spec)),
        _plain("frontend/src/main.jsx", "frontend-bootstrap", GeneratedArtifactType.FRONTEND, _frontend_main()),
        _bound(
            spec,
            "frontend/src/App.jsx",
            "crud-application-shell",
            GeneratedArtifactType.FRONTEND,
            _frontend_app(spec),
            ui_related=True,
        ),
        _bound(
            spec,
            "frontend/src/styles.css",
            "crud-application-styles",
            GeneratedArtifactType.FRONTEND,
            _frontend_css(),
            ui_related=True,
        ),
        _plain("backend/package.json", "backend-package", GeneratedArtifactType.CONFIGURATION, _backend_package(spec)),
        _bound(
            spec,
            "backend/src/app.js",
            "express-application",
            GeneratedArtifactType.API,
            _backend_app(spec),
            api_operation_ids=tuple(
                operation.operation_id
                for reference in api_references
                for operation in reference.operations
            ),
        ),
        _bound(
            spec,
            "backend/src/db/schema.sql",
            "crud-database-schema",
            GeneratedArtifactType.DATABASE,
            _sql_schema(spec),
            database_entity_ids=tuple(
                identity
                for reference in database_references
                for table in reference.tables
                for identity in (table.table_id, *(column.column_id for column in table.columns))
            ),
        ),
        _bound(
            spec,
            "api/openapi.yaml",
            "crud-openapi-definition",
            GeneratedArtifactType.API,
            _openapi(spec),
            api_operation_ids=tuple(
                operation.operation_id
                for reference in api_references
                for operation in reference.operations
            ),
        ),
    ]
    for entity in spec.entities:
        operations = _operation_ids(entity)
        seam = _seam_id(entity)
        stem = entity.variable_name
        artifacts.extend(
            (
                _entity_bound(
                    spec,
                    entity,
                    f"frontend/src/pages/{entity.class_name}Page.jsx",
                    f"{stem}-page",
                    GeneratedArtifactType.FRONTEND,
                    _entity_page(entity),
                    ui_related=True,
                ),
                _entity_bound(
                    spec,
                    entity,
                    f"frontend/src/components/{entity.class_name}Form.jsx",
                    f"{stem}-form-component",
                    GeneratedArtifactType.FRONTEND,
                    _entity_form(entity),
                    ui_related=True,
                ),
                _entity_bound(
                    spec,
                    entity,
                    f"frontend/src/components/{entity.class_name}List.jsx",
                    f"{stem}-list-component",
                    GeneratedArtifactType.FRONTEND,
                    _entity_list(entity),
                    ui_related=True,
                ),
                _entity_bound(
                    spec,
                    entity,
                    f"frontend/src/api/{stem}.js",
                    f"{stem}-api-client",
                    GeneratedArtifactType.API,
                    _entity_api(entity),
                    api_operation_ids=operations,
                ),
                _entity_bound(
                    spec,
                    entity,
                    f"backend/src/routes/{stem}Routes.js",
                    f"{stem}-routes",
                    GeneratedArtifactType.API,
                    _entity_routes(entity),
                    api_operation_ids=operations,
                ),
                _entity_bound(
                    spec,
                    entity,
                    f"backend/src/controllers/{stem}Controller.js",
                    f"{stem}-controller",
                    GeneratedArtifactType.CONTROLLER,
                    _entity_controller(entity),
                    api_operation_ids=operations,
                    safety_checked=True,
                ),
                _entity_bound(
                    spec,
                    entity,
                    f"backend/src/services/{stem}Service.js",
                    f"{stem}-service",
                    GeneratedArtifactType.BUSINESS_LOGIC,
                    _entity_service(entity),
                    test_seam_ids=(seam,),
                    safety_checked=True,
                    allow_secure_uuid=True,
                ),
                _entity_bound(
                    spec,
                    entity,
                    f"backend/src/repositories/{stem}Repository.js",
                    f"{stem}-repository-seam",
                    GeneratedArtifactType.REPOSITORY,
                    _entity_repository(entity),
                    test_seam_ids=(seam,),
                    safety_checked=True,
                ),
                _entity_bound(
                    spec,
                    entity,
                    f"backend/tests/{stem}Service.test.js",
                    f"{stem}-service-unit-test",
                    GeneratedArtifactType.TEST,
                    _entity_test(entity),
                    test_seam_ids=(seam,),
                ),
            )
        )
    return CrudRenderResult(
        artifacts=tuple(artifacts),
        api_references=api_references,
        database_references=database_references,
        test_seams=test_seams,
    )


def _plain(path: str, identity: str, kind: GeneratedArtifactType, content: str) -> TemplateArtifact:
    return TemplateArtifact(path, identity, kind, content)


def _bound(
    spec: CrudApplicationSpec,
    path: str,
    identity: str,
    kind: GeneratedArtifactType,
    content: str,
    *,
    ui_related: bool = False,
    api_operation_ids: tuple[str, ...] = (),
    database_entity_ids: tuple[str, ...] = (),
) -> TemplateArtifact:
    return TemplateArtifact(
        path,
        identity,
        kind,
        content,
        explicit_trace_bindings=True,
        requirement_ids=tuple(
            requirement_id
            for entity in spec.entities
            for requirement_id in entity.requirement_ids
        ),
        uml_ids=tuple(dict.fromkeys(entity.source_uml_id for entity in spec.entities)),
        design_anchor_ids=tuple(
            anchor_id for entity in spec.entities for anchor_id in entity.design_anchor_ids
        ),
        ui_artifact_ids=spec.source_ui_artifact_ids if ui_related else (),
        api_operation_ids=api_operation_ids,
        database_entity_ids=database_entity_ids,
    )


def _entity_bound(
    spec: CrudApplicationSpec,
    entity: CrudEntitySpec,
    path: str,
    identity: str,
    kind: GeneratedArtifactType,
    content: str,
    *,
    ui_related: bool = False,
    api_operation_ids: tuple[str, ...] = (),
    test_seam_ids: tuple[str, ...] = (),
    safety_checked: bool = False,
    allow_secure_uuid: bool = False,
) -> TemplateArtifact:
    return TemplateArtifact(
        path,
        identity,
        kind,
        content,
        explicit_trace_bindings=True,
        requirement_ids=entity.requirement_ids,
        uml_ids=(entity.source_uml_id,),
        design_anchor_ids=entity.design_anchor_ids,
        ui_artifact_ids=spec.source_ui_artifact_ids if ui_related else (),
        api_operation_ids=api_operation_ids,
        test_seam_ids=test_seam_ids,
        safety_checked=safety_checked,
        allow_secure_uuid=allow_secure_uuid,
    )


def _readme(spec: CrudApplicationSpec) -> str:
    entities = ", ".join(entity.class_name for entity in spec.entities)
    return f"""# {spec.application_name}\n\nGenerated from validated Component 3 input using CRUD spec {spec.spec_version}.\n\nEntities: {entities}.\n\nThe runtime repository mode is `IN_MEMORY`. `backend/src/db/schema.sql` is a\ndesign-only SQL artifact and does not prove database-backed persistence.\n\nGenerated code is untrusted and was not installed, built, tested, or executed\nautomatically. Use only an approved disposable environment for dependency\ninstallation, audit, build, and runtime checks.\n"""


def _frontend_package(spec: CrudApplicationSpec) -> str:
    return json.dumps(
        {
            "name": f"intelise-{spec.application_slug}-frontend",
            "private": True,
            "version": "0.1.0",
            "type": "module",
            "engines": {"node": ">=24.0.0 <25"},
            "scripts": {"dev": "vite", "build": "vite build"},
            "dependencies": {"react": "18.3.1", "react-dom": "18.3.1"},
            "devDependencies": {"@vitejs/plugin-react": "5.2.0", "vite": "8.3.4"},
        },
        indent=2,
    )


def _backend_package(spec: CrudApplicationSpec) -> str:
    return json.dumps(
        {
            "name": f"intelise-{spec.application_slug}-backend",
            "private": True,
            "version": "0.1.0",
            "type": "module",
            "engines": {"node": ">=24.0.0 <25"},
            "scripts": {"start": "node src/app.js", "test": "vitest run"},
            "dependencies": {"cors": "2.8.5", "express": "4.22.3"},
            "devDependencies": {"vitest": "4.1.12"},
        },
        indent=2,
    )


def _vite_config() -> str:
    return """import { defineConfig } from 'vite';
import react from '@vitejs/plugin-react';

export default defineConfig({ plugins: [react()] });
"""


def _index_html(spec: CrudApplicationSpec) -> str:
    return f"""<!doctype html>
<html lang="en">
  <head><meta charset="UTF-8" /><meta name="viewport" content="width=device-width, initial-scale=1.0" /><title>{spec.application_name}</title></head>
  <body><div id="root"></div><script type="module" src="/src/main.jsx"></script></body>
</html>
"""


def _frontend_main() -> str:
    return """import React from 'react';
import { createRoot } from 'react-dom/client';
import { App } from './App.jsx';
import './styles.css';

createRoot(document.getElementById('root')).render(<App />);
"""


def _frontend_app(spec: CrudApplicationSpec) -> str:
    imports = "\n".join(
        f"import {{ {entity.class_name}Page }} from './pages/{entity.class_name}Page.jsx';"
        for entity in spec.entities
    )
    page_rows = ",\n  ".join(
        "{ id: "
        + json.dumps(entity.route_segment)
        + ", label: "
        + json.dumps(_human_label(entity.plural_class_name))
        + f", component: {entity.class_name}Page }}"
        for entity in spec.entities
    )
    first = json.dumps(spec.entities[0].route_segment)
    return f"""import React, {{ useState }} from 'react';
{imports}

const pages = [
  {page_rows}
];

export function App() {{
  const [selected, setSelected] = useState({first});
  const active = pages.find((page) => page.id === selected) ?? pages[0];
  const ActivePage = active.component;
  return <div className="app-shell">
    <header><h1>{spec.application_name}</h1></header>
    <nav aria-label="Entity navigation">{{pages.map((page) => <button type="button" key={{page.id}} onClick={{() => setSelected(page.id)}} aria-current={{selected === page.id ? 'page' : undefined}}>{{page.label}}</button>)}}</nav>
    <ActivePage />
  </div>;
}}
"""


def _frontend_css() -> str:
    return """:root { font-family: Inter, system-ui, sans-serif; color: #172033; background: #f5f7fb; }
* { box-sizing: border-box; }
body { margin: 0; }
button, input { font: inherit; }
button { border: 1px solid #c8d2e4; border-radius: .5rem; background: white; color: #172033; }
button:hover { border-color: #2864ea; }
.app-shell { max-width: 1100px; margin: 0 auto; padding: 2rem; }
nav { display: flex; flex-wrap: wrap; gap: .5rem; margin-bottom: 1.5rem; }
nav button, form button, td button { padding: .6rem 1rem; cursor: pointer; }
nav button[aria-current='page'] { background: #2864ea; border-color: #2864ea; color: white; }
main { background: white; border: 1px solid #dfe5ef; border-radius: .8rem; padding: 1.5rem; }
form { display: grid; grid-template-columns: repeat(auto-fit, minmax(180px, 1fr)); align-items: end; gap: 1rem; margin-bottom: 1.5rem; }
label { display: grid; gap: .4rem; color: #475569; font-size: .9rem; }
label input:not([type='checkbox']) { width: 100%; min-height: 2.5rem; padding: .55rem .65rem; border: 1px solid #c8d2e4; border-radius: .45rem; color: #172033; }
.boolean-field { display: flex; align-items: center; align-self: center; gap: .55rem; min-height: 2.5rem; }
.boolean-field input { width: 1.1rem; height: 1.1rem; margin: 0; }
form > div { display: flex; align-items: center; gap: .5rem; min-height: 2.5rem; }
table { width: 100%; border-collapse: collapse; background: white; }
th, td { padding: .75rem; border-bottom: 1px solid #d8deea; text-align: left; }
[role='alert'] { color: #a11; }
@media (max-width: 640px) { .app-shell { padding: 1rem; } main { padding: 1rem; overflow-x: auto; } form { grid-template-columns: 1fr; } }
"""


def _entity_page(entity: CrudEntitySpec) -> str:
    name = entity.class_name
    variable = entity.variable_name
    plural = entity.plural_class_name
    return f"""import React, {{ useCallback, useEffect, useState }} from 'react';
import {{ {name}Form }} from '../components/{name}Form.jsx';
import {{ {name}List }} from '../components/{name}List.jsx';
import {{ create{name}, delete{name}, list{plural}, update{name} }} from '../api/{variable}.js';

export function {name}Page() {{
  const [items, setItems] = useState([]);
  const [editing, setEditing] = useState(null);
  const [error, setError] = useState('');
  const refresh = useCallback(async () => {{ try {{ setItems(await list{plural}()); setError(''); }} catch (problem) {{ setError(problem.message); }} }}, []);
  useEffect(() => {{ void refresh(); }}, [refresh]);
  const save = async (values) => {{
    if (editing) await update{name}(editing.id, values); else await create{name}(values);
    setEditing(null);
    await refresh();
  }};
  const remove = async (item) => {{ await delete{name}(item.id); if (editing?.id === item.id) setEditing(null); await refresh(); }};
  return <main>
    <h2>{_human_label(plural)}</h2>
    {{error && <p role="alert">{{error}}</p>}}
    <{name}Form initialValue={{editing}} onSubmit={{save}} onCancel={{() => setEditing(null)}} />
    <{name}List items={{items}} onEdit={{setEditing}} onDelete={{remove}} />
  </main>;
}}
"""


def _entity_form(entity: CrudEntitySpec) -> str:
    name = entity.class_name
    if name.lower() in ("calculation", "calculator"):
        return _calculator_form(name)
    mutable = [field for field in entity.fields if not field.generated]
    defaults = {
        field.name: False if field.scalar_type is CrudScalarType.BOOLEAN else ""
        for field in mutable
    }
    controls = "\n      ".join(_form_control(field) for field in mutable)
    payload = ",\n      ".join(
        f"{field.name}: {_form_value(field)}" for field in mutable
    )
    return f"""import React, {{ useEffect, useState }} from 'react';

const emptyValue = {json.dumps(defaults, separators=(',', ':'))};

export function {name}Form({{ initialValue, onSubmit, onCancel }}) {{
  const [value, setValue] = useState(emptyValue);
  useEffect(() => {{
    setValue(initialValue ? {{ ...emptyValue, ...initialValue }} : emptyValue);
  }}, [initialValue]);
  const change = (event) => {{
    const next = event.target.type === 'checkbox' ? event.target.checked : event.target.value;
    setValue((current) => ({{ ...current, [event.target.name]: next }}));
  }};
  const submit = async (event) => {{
    event.preventDefault();
    await onSubmit({{
      {payload}
    }});
    setValue(emptyValue);
  }};
  return <form onSubmit={{submit}}>
      {controls}
      <div><button type="submit">{{initialValue ? 'Update' : 'Create'}} {name}</button>{{initialValue && <button type="button" onClick={{onCancel}}>Cancel</button>}}</div>
    </form>;
}}
"""


def _calculator_form(name: str) -> str:
    return f"""import React, {{ useEffect, useState }} from 'react';

const emptyValue = {{"firstNumber":"","operation":"","secondNumber":"","result":"","status":""}};

export function {name}Form({{ initialValue, onSubmit, onCancel }}) {{
  const [display, setDisplay] = useState('0');
  const [firstNum, setFirstNum] = useState(null);
  const [op, setOp] = useState(null);
  const [clearOnNext, setClearOnNext] = useState(false);
  const [calcError, setCalcError] = useState('');

  const handleDigit = (digit) => {{
    setCalcError('');
    if (display === '0' || clearOnNext) {{
      setDisplay(String(digit));
      setClearOnNext(false);
    }} else {{
      setDisplay((prev) => prev + digit);
    }}
  }};

  const handleOp = (nextOp) => {{
    setCalcError('');
    setFirstNum(parseFloat(display));
    setOp(nextOp);
    setClearOnNext(true);
  }};

  const handleClear = () => {{
    setDisplay('0');
    setFirstNum(null);
    setOp(null);
    setClearOnNext(false);
    setCalcError('');
  }};

  const handleCalculate = async () => {{
    if (firstNum === null || op === null) return;
    const secondNum = parseFloat(display);
    let res = 0;
    let statusVal = 'SUCCESS';

    if (op === '+') res = firstNum + secondNum;
    else if (op === '-') res = firstNum - secondNum;
    else if (op === '*') res = firstNum * secondNum;
    else if (op === '/') {{
      if (secondNum === 0) {{
        statusVal = 'ERROR';
        setCalcError('Division by zero error');
        setDisplay('Error');
        await onSubmit({{
          firstNumber: firstNum,
          operation: op,
          secondNumber: secondNum,
          result: 0,
          status: 'ERROR'
        }});
        return;
      }}
      res = firstNum / secondNum;
    }}

    const roundedRes = Math.round(res * 1000000) / 1000000;
    setDisplay(String(roundedRes));
    setFirstNum(null);
    setOp(null);
    setClearOnNext(true);

    await onSubmit({{
      firstNumber: firstNum,
      operation: op,
      secondNumber: secondNum,
      result: roundedRes,
      status: statusVal
    }});
  }};

  return (
    <div className="calculator-widget" style={{{{ maxWidth: '340px', margin: '0 0 2rem 0', padding: '1.25rem', background: '#1e293b', borderRadius: '1rem', boxShadow: '0 10px 25px -5px rgba(0,0,0,0.3)', color: 'white' }}}}>
      <div style={{{{ background: '#0f172a', padding: '1rem', borderRadius: '0.6rem', textAlign: 'right', marginBottom: '1rem', minHeight: '4.5rem', display: 'flex', flexDirection: 'column', justifyContent: 'center' }}}}>
        <div style={{{{ fontSize: '0.85rem', color: '#94a3b8', minHeight: '1.2rem' }}}}>
          {{firstNum !== null && `${{firstNum}} ${{op}}`}}
        </div>
        <div style={{{{ fontSize: '1.85rem', fontWeight: 'bold', fontFamily: 'monospace', color: calcError ? '#f87171' : '#38bdf8', overflow: 'hidden', textOverflow: 'ellipsis' }}}}>
          {{display}}
        </div>
      </div>
      {{calcError && <div style={{{{ color: '#f87171', fontSize: '0.8rem', marginBottom: '0.5rem', textAlign: 'center' }}}}>{{calcError}}</div>}}
      <div style={{{{ display: 'grid', gridTemplateColumns: 'repeat(4, 1fr)', gap: '0.6rem' }}}}>
        <button type="button" onClick={{handleClear}} style={{{{ gridColumn: 'span 2', background: '#ef4444', color: 'white', border: 'none', borderRadius: '0.5rem', padding: '0.85rem', fontSize: '1.1rem', cursor: 'pointer', fontWeight: 'bold' }}}}>C</button>
        <button type="button" onClick={{() => handleOp('/')}} style={{{{ background: '#f59e0b', color: 'white', border: 'none', borderRadius: '0.5rem', padding: '0.85rem', fontSize: '1.2rem', cursor: 'pointer', fontWeight: 'bold' }}}}>÷</button>
        <button type="button" onClick={{() => handleOp('*')}} style={{{{ background: '#f59e0b', color: 'white', border: 'none', borderRadius: '0.5rem', padding: '0.85rem', fontSize: '1.2rem', cursor: 'pointer', fontWeight: 'bold' }}}}>×</button>

        <button type="button" onClick={{() => handleDigit('7')}} style={{{{ background: '#334155', color: 'white', border: 'none', borderRadius: '0.5rem', padding: '0.85rem', fontSize: '1.2rem', cursor: 'pointer' }}}}>7</button>
        <button type="button" onClick={{() => handleDigit('8')}} style={{{{ background: '#334155', color: 'white', border: 'none', borderRadius: '0.5rem', padding: '0.85rem', fontSize: '1.2rem', cursor: 'pointer' }}}}>8</button>
        <button type="button" onClick={{() => handleDigit('9')}} style={{{{ background: '#334155', color: 'white', border: 'none', borderRadius: '0.5rem', padding: '0.85rem', fontSize: '1.2rem', cursor: 'pointer' }}}}>9</button>
        <button type="button" onClick={{() => handleOp('-')}} style={{{{ background: '#f59e0b', color: 'white', border: 'none', borderRadius: '0.5rem', padding: '0.85rem', fontSize: '1.2rem', cursor: 'pointer', fontWeight: 'bold' }}}}>−</button>

        <button type="button" onClick={{() => handleDigit('4')}} style={{{{ background: '#334155', color: 'white', border: 'none', borderRadius: '0.5rem', padding: '0.85rem', fontSize: '1.2rem', cursor: 'pointer' }}}}>4</button>
        <button type="button" onClick={{() => handleDigit('5')}} style={{{{ background: '#334155', color: 'white', border: 'none', borderRadius: '0.5rem', padding: '0.85rem', fontSize: '1.2rem', cursor: 'pointer' }}}}>5</button>
        <button type="button" onClick={{() => handleDigit('6')}} style={{{{ background: '#334155', color: 'white', border: 'none', borderRadius: '0.5rem', padding: '0.85rem', fontSize: '1.2rem', cursor: 'pointer' }}}}>6</button>
        <button type="button" onClick={{() => handleOp('+')}} style={{{{ background: '#f59e0b', color: 'white', border: 'none', borderRadius: '0.5rem', padding: '0.85rem', fontSize: '1.2rem', cursor: 'pointer', fontWeight: 'bold' }}}}>+</button>

        <button type="button" onClick={{() => handleDigit('1')}} style={{{{ background: '#334155', color: 'white', border: 'none', borderRadius: '0.5rem', padding: '0.85rem', fontSize: '1.2rem', cursor: 'pointer' }}}}>1</button>
        <button type="button" onClick={{() => handleDigit('2')}} style={{{{ background: '#334155', color: 'white', border: 'none', borderRadius: '0.5rem', padding: '0.85rem', fontSize: '1.2rem', cursor: 'pointer' }}}}>2</button>
        <button type="button" onClick={{() => handleDigit('3')}} style={{{{ background: '#334155', color: 'white', border: 'none', borderRadius: '0.5rem', padding: '0.85rem', fontSize: '1.2rem', cursor: 'pointer' }}}}>3</button>
        <button type="button" onClick={{handleCalculate}} style={{{{ gridRow: 'span 2', background: '#3b82f6', color: 'white', border: 'none', borderRadius: '0.5rem', padding: '0.85rem', fontSize: '1.3rem', cursor: 'pointer', fontWeight: 'bold' }}}}>=</button>

        <button type="button" onClick={{() => handleDigit('0')}} style={{{{ gridColumn: 'span 2', background: '#334155', color: 'white', border: 'none', borderRadius: '0.5rem', padding: '0.85rem', fontSize: '1.2rem', cursor: 'pointer' }}}}>0</button>
        <button type="button" onClick={{() => handleDigit('.')}} style={{{{ background: '#334155', color: 'white', border: 'none', borderRadius: '0.5rem', padding: '0.85rem', fontSize: '1.2rem', cursor: 'pointer' }}}}>.</button>
      </div>
    </div>
  );
}}
"""


def _form_control(field: CrudFieldSpec) -> str:
    label = _human_label(field.name)
    if field.scalar_type is CrudScalarType.BOOLEAN:
        return f"<label className=\"boolean-field\"><input name=\"{field.name}\" type=\"checkbox\" checked={{Boolean(value.{field.name})}} onChange={{change}} /> <span>{label}</span></label>"
    step = ' step="1"' if field.scalar_type is CrudScalarType.INTEGER else (
        ' step="any"' if field.scalar_type is CrudScalarType.NUMBER else ""
    )
    return f"<label>{label}<input name=\"{field.name}\" type=\"{field.input_control}\"{step} required value={{value.{field.name}}} onChange={{change}} /></label>"


def _form_value(field: CrudFieldSpec) -> str:
    if field.scalar_type is CrudScalarType.STRING:
        return f"value.{field.name}.trim()"
    if field.scalar_type is CrudScalarType.INTEGER:
        return f"Number.parseInt(value.{field.name}, 10)"
    if field.scalar_type is CrudScalarType.NUMBER:
        return f"Number(value.{field.name})"
    if field.scalar_type is CrudScalarType.BOOLEAN:
        return f"Boolean(value.{field.name})"
    return f"value.{field.name}"


def _entity_list(entity: CrudEntitySpec) -> str:
    headers = "".join(f"<th>{_human_label(field.name)}</th>" for field in entity.fields)
    cells = "".join(
        f"<td>{{{_display_expression(field)}}}</td>" for field in entity.fields
    )
    name = entity.class_name
    return f"""import React from 'react';

export function {name}List({{ items, onEdit, onDelete }}) {{
  if (items.length === 0) return <p>No {_human_label(entity.plural_class_name).casefold()} yet.</p>;
  return <table><thead><tr>{headers}<th>Actions</th></tr></thead><tbody>{{items.map((item) => <tr key={{item.id}}>{cells}<td><button type="button" onClick={{() => onEdit(item)}}>Edit</button><button type="button" onClick={{() => onDelete(item)}}>Delete</button></td></tr>)}}</tbody></table>;
}}
"""


def _display_expression(field: CrudFieldSpec) -> str:
    if field.scalar_type is CrudScalarType.BOOLEAN:
        return f"item.{field.name} ? 'Yes' : 'No'"
    return f"item.{field.name}"


def _entity_api(entity: CrudEntitySpec) -> str:
    name = entity.class_name
    plural = entity.plural_class_name
    return f"""const configuredApiOrigin = import.meta.env.VITE_API_BASE_URL ?? 'http://127.0.0.1:3001';
const API_ORIGIN = configuredApiOrigin.endsWith('/') ? configuredApiOrigin.slice(0, -1) : configuredApiOrigin;
const API_BASE = `${{API_ORIGIN}}/api/v1/{entity.route_segment}`;

async function request(url, options) {{
  const response = await fetch(url, {{ headers: {{ 'Content-Type': 'application/json' }}, ...options }});
  const payload = response.status === 204 ? null : await response.json();
  if (!response.ok) throw new Error(payload?.error?.message ?? `{name} API failed with ${{response.status}}`);
  return payload;
}}

export const list{plural} = () => request(API_BASE);
export const create{name} = (value) => request(API_BASE, {{ method: 'POST', body: JSON.stringify(value) }});
export const update{name} = (id, value) => request(`${{API_BASE}}/${{id}}`, {{ method: 'PATCH', body: JSON.stringify(value) }});
export const delete{name} = (id) => request(`${{API_BASE}}/${{id}}`, {{ method: 'DELETE' }});
"""


def _backend_app(spec: CrudApplicationSpec) -> str:
    imports: list[str] = ["import cors from 'cors';", "import express from 'express';"]
    setup: list[str] = []
    mounts: list[str] = []
    for entity in spec.entities:
        stem = entity.variable_name
        name = entity.class_name
        imports.extend(
            (
                f"import {{ create{name}Controller }} from './controllers/{stem}Controller.js';",
                f"import {{ InMemory{name}Repository }} from './repositories/{stem}Repository.js';",
                f"import {{ create{name}Routes }} from './routes/{stem}Routes.js';",
                f"import {{ create{name}Service }} from './services/{stem}Service.js';",
            )
        )
        setup.extend(
            (
                f"const {stem}Repository = new InMemory{name}Repository();",
                f"const {stem}Service = create{name}Service({stem}Repository);",
            )
        )
        mounts.append(
            f"app.use('/api/v1/{entity.route_segment}', create{name}Routes(create{name}Controller({stem}Service)));"
        )
    return "\n".join(imports) + "\n\n" + "\n".join(
        (
            "const app = express();",
            "const allowedOrigin = process.env.CORS_ALLOWED_ORIGIN ?? 'http://127.0.0.1:5173';",
            "const host = process.env.HOST ?? '127.0.0.1';",
            "const port = Number.parseInt(process.env.PORT ?? '3001', 10);",
            *setup,
            "app.use(cors({ origin: allowedOrigin, methods: ['GET', 'POST', 'PATCH', 'DELETE'] }));",
            "app.use(express.json({ limit: '32kb' }));",
            *mounts,
            "app.use((error, _request, response, _next) => {",
            "  const statusCode = Number.isInteger(error.statusCode) ? error.statusCode : 500;",
            "  const code = typeof error.code === 'string' ? error.code : 'INTERNAL_ERROR';",
            "  const message = statusCode === 500 ? 'Internal server error.' : error.message;",
            "  response.status(statusCode).json({ error: { code, message } });",
            "});",
            "app.listen(port, host);",
            "",
        )
    )


def _entity_routes(entity: CrudEntitySpec) -> str:
    name = entity.class_name
    return f"""import {{ Router }} from 'express';

const asyncHandler = (handler) => (request, response, next) => {{
  Promise.resolve(handler(request, response, next)).catch(next);
}};

export function create{name}Routes(controller) {{
  const router = Router();
  router.get('/', asyncHandler(controller.list));
  router.post('/', asyncHandler(controller.create));
  router.patch('/:id', asyncHandler(controller.update));
  router.delete('/:id', asyncHandler(controller.remove));
  return router;
}}
"""


def _entity_controller(entity: CrudEntitySpec) -> str:
    name = entity.class_name
    return f"""export function create{name}Controller(service) {{
  return {{
    list: async (_request, response) => response.json(await service.list()),
    create: async (request, response) => response.status(201).json(await service.create(request.body)),
    update: async (request, response) => response.json(await service.update(request.params.id, request.body)),
    remove: async (request, response) => {{ await service.remove(request.params.id); response.status(204).end(); }},
  }};
}}
"""


def _entity_service(entity: CrudEntitySpec) -> str:
    name = entity.class_name
    code = entity.class_name.upper() + "_NOT_FOUND"
    invalid = "INVALID_" + entity.class_name.upper() + "_INPUT"
    mutable = [field for field in entity.fields if not field.generated]
    allowed = json.dumps([field.name for field in mutable], separators=(",", ":"))
    validations = "\n".join(_service_validation(field, invalid) for field in mutable)
    clean_fields = ", ".join(field.name for field in mutable)
    return f"""export function create{name}Service(repository) {{
  const isUuid = (id) => {{
    if (typeof id !== 'string' || id.length !== 36) return false;
    const value = id.toLowerCase();
    const compact = value.replaceAll('-', '');
    const isHex = Array.from(compact).every((character) => '0123456789abcdef'.includes(character));
    return value.charAt(8) === '-' && value.charAt(13) === '-' && value.charAt(18) === '-' && value.charAt(23) === '-' && compact.length === 32 && isHex && '12345'.includes(value.charAt(14)) && '89ab'.includes(value.charAt(19));
  }};
  const fail = (statusCode, code, message) => {{
    const error = new Error(message);
    error.statusCode = statusCode;
    error.code = code;
    throw error;
  }};
  const requireId = (id) => {{
    if (!isUuid(id)) fail(400, '{invalid}', 'id must be a UUID.');
  }};
  const validateInput = (input, partial) => {{
    if (!input || typeof input !== 'object' || Array.isArray(input)) fail(400, '{invalid}', 'request body must be an object.');
    const allowed = {allowed};
    if (Object.keys(input).some((field) => !allowed.includes(field))) fail(400, '{invalid}', 'request contains an unknown field.');
    if (partial && Object.keys(input).length === 0) fail(400, '{invalid}', 'update requires at least one field.');
    const clean = {{}};
{validations}
    return clean;
  }};
  return {{
    list: () => repository.list(),
    create: (input) => {{
      const {{ {clean_fields} }} = validateInput(input, false);
      const id = globalThis.crypto.randomUUID();
      const value = {{ id, {clean_fields} }};
      return repository.create(value);
    }},
    update: async (id, changes) => {{
      requireId(id);
      if (!(await repository.findById(id))) fail(404, '{code}', '{name} not found.');
      return repository.update(id, validateInput(changes, true));
    }},
    remove: async (id) => {{
      requireId(id);
      if (!(await repository.findById(id))) fail(404, '{code}', '{name} not found.');
      return repository.remove(id);
    }},
  }};
}}
"""


def _service_validation(field: CrudFieldSpec, invalid_code: str) -> str:
    present = f"Object.hasOwn(input, '{field.name}')"
    prefix = f"    if (!partial || {present}) {{"
    value = f"input.{field.name}"
    invalid = {
        CrudScalarType.STRING: f"typeof {value} !== 'string' || !{value}.trim()",
        CrudScalarType.INTEGER: f"!Number.isInteger({value})",
        CrudScalarType.NUMBER: f"typeof {value} !== 'number' || !Number.isFinite({value})",
        CrudScalarType.BOOLEAN: f"typeof {value} !== 'boolean'",
        CrudScalarType.DATE: f"typeof {value} !== 'string' || !/^\\d{{4}}-\\d{{2}}-\\d{{2}}$/.test({value})",
    }[field.scalar_type]
    normalized = f"{value}.trim()" if field.scalar_type is CrudScalarType.STRING else value
    return "\n".join(
        (
            prefix,
            f"      if ({invalid}) fail(400, '{invalid_code}', '{field.name} has an invalid value.');",
            f"      clean.{field.name} = {normalized};",
            "    }",
        )
    )


def _entity_repository(entity: CrudEntitySpec) -> str:
    name = entity.class_name
    return f"""// Runtime persistence mode: IN_MEMORY. This does not use schema.sql.
export class InMemory{name}Repository {{
  constructor() {{ this.records = new Map(); }}
  async list() {{ return [...this.records.values()]; }}
  async findById(id) {{ return this.records.get(id) ?? null; }}
  async create(value) {{ this.records.set(value.id, value); return value; }}
  async update(id, changes) {{ const value = {{ ...(await this.findById(id)), ...changes, id }}; this.records.set(id, value); return value; }}
  async remove(id) {{ return this.records.delete(id); }}
}}
"""


def _entity_test(entity: CrudEntitySpec) -> str:
    name = entity.class_name
    stem = entity.variable_name
    payload = ", ".join(
        f"{field.name}: {_sample_js(field)}" for field in entity.fields if not field.generated
    )
    return f"""import {{ describe, expect, it, vi }} from 'vitest';
import {{ create{name}Service }} from '../src/services/{stem}Service.js';

describe('{_human_label(name).casefold()} service repository seam', () => {{
  it('creates through an injected repository', async () => {{
    const repository = {{ create: vi.fn(async (value) => value), list: vi.fn(), findById: vi.fn(), update: vi.fn(), remove: vi.fn() }};
    const value = await create{name}Service(repository).create({{ {payload} }});
    expect(repository.create).toHaveBeenCalledOnce();
    expect(value.id).toMatch(/^[0-9a-f-]{{36}}$/i);
  }});
}});
"""


def _sample_js(field: CrudFieldSpec) -> str:
    return {
        CrudScalarType.STRING: json.dumps(f"Sample {field.name}"),
        CrudScalarType.INTEGER: "3",
        CrudScalarType.NUMBER: "12.5",
        CrudScalarType.BOOLEAN: "true",
        CrudScalarType.DATE: "'2026-10-19'",
    }[field.scalar_type]


def _sql_schema(spec: CrudApplicationSpec) -> str:
    blocks = ["-- Design-only SQL artifact. Runtime repository mode is IN_MEMORY."]
    for entity in spec.entities:
        columns = []
        for field in entity.fields:
            sql_type = {
                CrudScalarType.STRING: "TEXT",
                CrudScalarType.INTEGER: "INTEGER",
                CrudScalarType.NUMBER: "REAL",
                CrudScalarType.BOOLEAN: "INTEGER",
                CrudScalarType.DATE: "TEXT",
            }[field.scalar_type]
            suffix = " PRIMARY KEY" if field.generated else " NOT NULL"
            if field.scalar_type is CrudScalarType.BOOLEAN:
                suffix += f" CHECK ({field.name} IN (0, 1))"
            columns.append(f"  {field.name} {sql_type}{suffix}")
        blocks.append(
            f"CREATE TABLE IF NOT EXISTS {entity.table_name} (\n"
            + ",\n".join(columns)
            + "\n);"
        )
    return "\n\n".join(blocks) + "\n"


def _openapi(spec: CrudApplicationSpec) -> str:
    paths: dict[str, object] = {}
    schemas: dict[str, object] = {}
    for entity in spec.entities:
        name = entity.class_name
        collection = f"/api/v1/{entity.route_segment}"
        item = collection + "/{id}"
        operations = _operation_ids(entity)
        schemas[name] = _entity_schema(entity, include_id=True, partial=False)
        schemas[f"Create{name}Request"] = _entity_schema(entity, include_id=False, partial=False)
        schemas[f"Update{name}Request"] = _entity_schema(entity, include_id=False, partial=True)
        paths[collection] = {
            "get": {
                "operationId": operations[0],
                "responses": {"200": {"description": f"{name} list", "content": {"application/json": {"schema": {"type": "array", "items": {"$ref": f"#/components/schemas/{name}"}}}}}},
            },
            "post": {
                "operationId": operations[1],
                "requestBody": {"required": True, "content": {"application/json": {"schema": {"$ref": f"#/components/schemas/Create{name}Request"}}}},
                "responses": {"201": {"description": f"Created {name}", "content": {"application/json": {"schema": {"$ref": f"#/components/schemas/{name}"}}}}, "400": {"$ref": "#/components/responses/BadRequest"}},
            },
        }
        paths[item] = {
            "patch": {
                "operationId": operations[2],
                "parameters": [{"name": "id", "in": "path", "required": True, "schema": {"type": "string", "format": "uuid"}}],
                "requestBody": {"required": True, "content": {"application/json": {"schema": {"$ref": f"#/components/schemas/Update{name}Request"}}}},
                "responses": {"200": {"description": f"Updated {name}", "content": {"application/json": {"schema": {"$ref": f"#/components/schemas/{name}"}}}}, "400": {"$ref": "#/components/responses/BadRequest"}, "404": {"$ref": "#/components/responses/NotFound"}},
            },
            "delete": {
                "operationId": operations[3],
                "parameters": [{"name": "id", "in": "path", "required": True, "schema": {"type": "string", "format": "uuid"}}],
                "responses": {"204": {"description": f"Deleted {name}"}, "400": {"$ref": "#/components/responses/BadRequest"}, "404": {"$ref": "#/components/responses/NotFound"}},
            },
        }
    schemas["ErrorResponse"] = {
        "type": "object",
        "required": ["error"],
        "properties": {"error": {"type": "object", "required": ["code", "message"], "properties": {"code": {"type": "string"}, "message": {"type": "string"}}}},
    }
    document = {
        "openapi": "3.1.0",
        "info": {"title": f"{spec.application_name} API", "version": "1.0.0"},
        "paths": paths,
        "components": {
            "schemas": schemas,
            "responses": {
                "BadRequest": {"description": "Invalid input", "content": {"application/json": {"schema": {"$ref": "#/components/schemas/ErrorResponse"}}}},
                "NotFound": {"description": "Entity not found", "content": {"application/json": {"schema": {"$ref": "#/components/schemas/ErrorResponse"}}}},
            },
        },
    }
    return json.dumps(document, indent=2)


def _entity_schema(entity: CrudEntitySpec, *, include_id: bool, partial: bool) -> dict:
    fields = [field for field in entity.fields if include_id or not field.generated]
    schema: dict[str, object] = {
        "type": "object",
        "additionalProperties": False,
        "properties": {field.name: _openapi_field(field) for field in fields},
    }
    if not partial:
        schema["required"] = [field.name for field in fields]
    else:
        schema["minProperties"] = 1
    return schema


def _openapi_field(field: CrudFieldSpec) -> dict:
    if field.generated:
        return {"type": "string", "format": "uuid"}
    if field.scalar_type is CrudScalarType.STRING:
        return {"type": "string", "minLength": 1}
    if field.scalar_type is CrudScalarType.INTEGER:
        return {"type": "integer"}
    if field.scalar_type is CrudScalarType.NUMBER:
        return {"type": "number"}
    if field.scalar_type is CrudScalarType.BOOLEAN:
        return {"type": "boolean"}
    return {"type": "string", "format": "date"}


def _api_references(spec: CrudApplicationSpec) -> tuple[ApiArtifactReference, ...]:
    references = []
    for entity in spec.entities:
        operations = _operation_ids(entity)
        collection = f"/api/v1/{entity.route_segment}"
        references.append(
            ApiArtifactReference(
                reference_id=f"API-{_identity(entity.class_name)}-V1",
                definition_path="api/openapi.yaml",
                operations=(
                    ApiOperationIdentity(operation_id=operations[0], method="GET", route_path=collection, success_response_schema=f"{entity.class_name}[]", success_status=200),
                    ApiOperationIdentity(operation_id=operations[1], method="POST", route_path=collection, request_schema=f"Create{entity.class_name}Request", success_response_schema=entity.class_name, success_status=201),
                    ApiOperationIdentity(operation_id=operations[2], method="PATCH", route_path=collection + "/{id}", request_schema=f"Update{entity.class_name}Request", success_response_schema=entity.class_name, success_status=200),
                    ApiOperationIdentity(operation_id=operations[3], method="DELETE", route_path=collection + "/{id}", success_status=204),
                ),
            )
        )
    return tuple(references)


def _database_references(spec: CrudApplicationSpec) -> tuple[DatabaseArtifactReference, ...]:
    tables = []
    for entity in spec.entities:
        table_id = _table_id(entity)
        tables.append(
            DatabaseTableIdentity(
                table_id=table_id,
                name=entity.table_name,
                columns=tuple(
                    DatabaseColumnIdentity(
                        column_id=_column_id(entity, field),
                        name=field.name,
                        data_type={
                            CrudScalarType.STRING: "TEXT",
                            CrudScalarType.INTEGER: "INTEGER",
                            CrudScalarType.NUMBER: "REAL",
                            CrudScalarType.BOOLEAN: "INTEGER_BOOLEAN",
                            CrudScalarType.DATE: "DATE_TEXT",
                        }[field.scalar_type],
                        nullable=False,
                        primary_key=field.generated,
                    )
                    for field in entity.fields
                ),
            )
        )
    return (
        DatabaseArtifactReference(
            reference_id=f"DB-{_identity(spec.application_slug)}-V1",
            script_path="backend/src/db/schema.sql",
            tables=tuple(tables),
        ),
    )


def _test_seams(spec: CrudApplicationSpec) -> tuple[TestSeamReference, ...]:
    return tuple(
        TestSeamReference(
            reference_id=_seam_id(entity),
            module_path=f"backend/src/repositories/{entity.variable_name}Repository.js",
            description=(
                f"create{entity.class_name}Service receives a repository implementing "
                "list, findById, create, update, and remove; tests can inject a mock."
            ),
        )
        for entity in spec.entities
    )


def _operation_ids(entity: CrudEntitySpec) -> tuple[str, str, str, str]:
    token = _identity(entity.class_name)
    return tuple(f"API-OP-{token}-{operation}" for operation in ("LIST", "CREATE", "UPDATE", "DELETE"))  # type: ignore[return-value]


def _table_id(entity: CrudEntitySpec) -> str:
    return f"DB-TABLE-{_identity(entity.table_name)}"


def _column_id(entity: CrudEntitySpec, field: CrudFieldSpec) -> str:
    return f"DB-COLUMN-{_identity(entity.table_name)}-{_identity(field.name)}"


def _seam_id(entity: CrudEntitySpec) -> str:
    return f"SEAM-{_identity(entity.class_name)}-REPOSITORY"


def _identity(value: str) -> str:
    return re.sub(r"[^A-Z0-9]+", "-", value.upper()).strip("-")


def _human_label(value: str) -> str:
    return re.sub(r"(?<=[a-z0-9])(?=[A-Z])", " ", value).replace("_", " ").title()
