# CodeBERT fine-tuning for PlantUML syntax validation (InteliSE Component 2)

Run order (details and explanations are in the chat answer):

| Step | Script | Where to run | Output |
|---|---|---|---|
| 0 (smoke test) | `step0_make_demo_data.py` | laptop | fake XMI + `data/manifest.csv` |
| 1 | `step1_select_models.py` | laptop | `data/manifest.csv` (real ModelSet) |
| 2 | `step2_xmi_to_plantuml.py` | laptop | `data/puml/*.puml`, `data/converted.csv` |
| 3 | `step3_check_and_filter.py` | laptop | `data/clean.csv` |
| 4 | `step4_make_mutations.py` | laptop | `data/syntax_dataset.csv` |
| 5 | `step5_split.py` | laptop | `data/splits/{train,val,test}.csv` |
| 6 | `step6_train_codebert.py` | Colab/Kaggle GPU | `models/codebert-uml-syntax/` |
| 7 | `step7_evaluate.py` | GPU or laptop | `results/test_metrics.json` ... |
| 8 | `uml_syntax_validator.py` | laptop (service) | JSON validation report + refinement prompt |
| 9 | `step9_collect_qwen_outputs.py` | laptop + Qwen | `data/qwen_outputs.csv` (real-error test set) |

Setup:
```
pip install -r requirements.txt
# put plantuml.jar (e.g. v1.2025.4 from github.com/plantuml/plantuml/releases) in tools/
java -cp tools/plantuml.jar tools/PumlChecker.java   # Java 11+; type a .puml path, get VALID/ERROR
```

Smoke test (about 1 minute, no GPU):
```
python step0_make_demo_data.py
python step2_xmi_to_plantuml.py
python step3_check_and_filter.py
python step4_make_mutations.py
python step5_split.py
python step6_train_codebert.py --max_train_samples 300 --epochs 1 --batch 8
python step7_evaluate.py
```

Real data:
```
git clone https://github.com/modelset/modelset-dataset
# raw XMI: see modelset-dataset/bin/download-data.sh (repo-genmymodel-uml.tar.gz), extract into raw-data/
python step1_select_models.py --db modelset-dataset/datasets/dataset.genmymodel/data/genmymodel.db --raw raw-data
```
ModelSet is LGPL-3.0: cite it (Hernández López et al., SoSyM 2022) and record the version you used.
