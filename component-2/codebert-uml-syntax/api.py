"""Web API for Component 2 - the React frontend talks to this file.

    POST /generate      SRS -> Qwen -> validator -> repair loop (takes a few minutes)
    POST /validate      check one PlantUML diagram (fast, no LLM)
    GET  /runs          list of saved runs
    GET  /runs/{id}     one saved run with every round

Every /generate run is saved in a small SQLite database (component2.db).

Start it from the codebert-uml-syntax folder:
    pip install fastapi uvicorn
    uvicorn api:app --port 8000
"""
import json
import sqlite3
import subprocess
import time
from pathlib import Path

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

from llm_client import DEFAULT_MODEL, is_running
from run_pipeline import for_display, run_one
from uml_syntax_validator import SyntaxValidator

MODEL_DIR = "models/codebert-uml-syntax-s42"
OUT_DIR = Path("outputs/web")
DB_FILE = "component2.db"

app = FastAPI()
# the React dev server runs on another port, so the browser needs permission to call us
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])

validator = SyntaxValidator(MODEL_DIR)       # load CodeBERT once, not on every request

db = sqlite3.connect(DB_FILE, check_same_thread=False)
db.row_factory = sqlite3.Row                 # rows behave like dicts
db.execute("""CREATE TABLE IF NOT EXISTS runs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    created TEXT, project TEXT, diagram_type TEXT, srs TEXT,
    valid_first INTEGER, valid_final INTEGER, rounds TEXT)""")


class GenerateRequest(BaseModel):
    srs: str
    diagram_type: str = "CLASS"              # or "USE_CASE"
    project: str = "web"
    max_rounds: int = 3


class ValidateRequest(BaseModel):
    puml: str
    diagram_type: str | None = None          # None = guess from the diagram


def render_svg(puml):
    """Draw the diagram with PlantUML and return it as SVG text."""
    result = subprocess.run(["java", "-jar", "tools/plantuml.jar", "-tsvg", "-pipe", "-charset", "UTF-8"],
                            input=puml.encode("utf-8"), capture_output=True)
    return result.stdout.decode("utf-8", errors="ignore")


@app.post("/generate")
def generate(req: GenerateRequest):
    if not is_running():
        raise HTTPException(503, "Ollama is not running. Start the Ollama app first.")
    row = run_one(validator, req.srs, req.diagram_type, req.project, OUT_DIR,
                  DEFAULT_MODEL, req.max_rounds, 0.0)

    # run_one saved every round as <project>_<type>_r<n>.puml; read them back
    errors = row["error_types"].split(";") if row["error_types"] else []
    rounds = []
    for n in range(row["rounds"] + 1):
        puml = (OUT_DIR / f"{req.project}_{req.diagram_type}_r{n}.puml").read_text(encoding="utf-8")
        status = errors[n] if n < len(errors) else "VALID"
        # check the round again so the page can show what each check found
        # (the skinparam line was only added for drawing, so take it out first)
        report = validator.validate(puml.replace("skinparam classAttributeIconSize 0\n", "", 1), req.diagram_type)
        if status != "VALID" and not report["flagged_by"]:
            report["flagged_by"] = ["repair_check"]      # the pipeline sent it back (fix not done)
        rounds.append({"round": n, "status": status, "puml": puml, "svg": render_svg(puml),
                       "feedback": report["feedback"], "flagged_by": report["flagged_by"],
                       "codebert": report["codebert"]})

    cur = db.execute("INSERT INTO runs (created, project, diagram_type, srs, valid_first, valid_final, rounds) "
                     "VALUES (?, ?, ?, ?, ?, ?, ?)",
                     (time.strftime("%Y-%m-%d %H:%M"), req.project, req.diagram_type, req.srs,
                      row["valid_first_try"], row["valid_final"], json.dumps(rounds)))
    db.commit()
    return get_run(cur.lastrowid)


@app.post("/validate")
def validate(req: ValidateRequest):
    report = validator.validate(req.puml, req.diagram_type)
    report["svg"] = render_svg(for_display(report["plantuml_source"]))
    return report


@app.get("/runs")
def list_runs():
    rows = db.execute("SELECT id, created, project, diagram_type, valid_first, valid_final "
                      "FROM runs ORDER BY id DESC").fetchall()
    return [dict(r) for r in rows]


@app.get("/runs/{run_id}")
def get_run(run_id: int):
    row = db.execute("SELECT * FROM runs WHERE id = ?", (run_id,)).fetchone()
    if row is None:
        raise HTTPException(404, "Run not found")
    run = dict(row)
    run["rounds"] = json.loads(run["rounds"])
    return run