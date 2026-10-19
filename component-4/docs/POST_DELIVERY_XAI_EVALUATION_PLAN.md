# INTELISE Component 4 — Post-Delivery Code Understanding XAI Evaluation Plan

## 1. Research Background & Objectives

This evaluation protocol defines the formal experimental framework to assess the redesigned human-facing Explainable AI (XAI) subsystem of INTELISE Component 4. 

### 1.1 Context & Research Gap
Prior automated software engineering research often conflates machine-directed error tracing with human-facing explainability. When an LLM generates candidate code that fails unit tests, presenting intermediate assertion errors, tracebacks, and repair hypotheses to the end user causes significant cognitive overload and disorientation. The end user did not author the code and cannot manually intervene in intermediate generation cycles.

By refocusing human-facing XAI on **Post-Delivery Code Understanding**—unlocked exclusively after candidate code has passed 100% of test oracles, satisfied deployment-readiness governance, and been delivered—Component 4 aims to maximize software comprehensibility, architectural clarity, and operational trust while reducing extraneous cognitive load.

### 1.2 Formal Research Question & Hypotheses

- **Primary Research Question (RQ3)**: *To what extent does a gated, dual-level post-delivery code explanation system improve user comprehension, reduce cognitive burden, and maintain zero hallucination compared to intermediate defect-oriented explanations?*

- **Hypothesis 1 ($H_1$ — Comprehension Gain)**: Users provided with post-delivery code explanations demonstrate a statistically significant increase in comprehension quiz accuracy ($p < 0.01$) compared to baseline users inspecting raw code and docstrings.
- **Hypothesis 2 ($H_2$ — Cognitive Load Reduction)**: Post-delivery explanation gating significantly reduces subjective cognitive load as measured by NASA-TLX ($p < 0.001$) compared to intermediate defect streaming.
- **Hypothesis 3 ($H_3$ — Zero-Hallucination Integrity)**: Deterministic AST-grounded synthesis achieves a 0.0% code hallucination rate across all 8 explanatory dimensions.

---

## 2. Evaluation Metrics Taxonomy

The evaluation framework employs a multi-methodological approach combining automated formal verification with human subject experimental trials.

```
+----------------------------------------------------------------------------------------------------+
|                                    EVALUATION METRIC TAXONOMY                                      |
+--------------------------+-----------------------+-------------------------------------------------+
| Metric                   | Evaluation Method     | Formula / Operationalization                    |
+--------------------------+-----------------------+-------------------------------------------------+
| 1. Factual Accuracy      | Automated + Expert    | Proportion of explanatory statements verified   |
|    ($\text{Acc}_{\text{XAI}}$) | Review                | against static AST & runtime traces ($E/T$).    |
|                          |                       | Target: $\ge 98.0\%$.                           |
+--------------------------+-----------------------+-------------------------------------------------+
| 2. Code Traceability     | Automated AST Mapping | Percentage of AST functions, parameters, and    |
|    ($\text{Trace}$)      |                       | classes mapped to explanatory nodes.            |
|                          |                       | Target: $100.0\%$.                              |
+--------------------------+-----------------------+-------------------------------------------------+
| 3. Hallucination Rate    | Automated AST Scan    | Fabricated functions, classes, or dependencies  |
|    ($\text{Halluc}$)     |                       | cited in XAI output divided by total entities.  |
|                          |                       | Target: $0.00\%$.                               |
+--------------------------+-----------------------+-------------------------------------------------+
| 4. Completeness          | Automated Dimension   | Presence and non-vacuity of all 8 required      |
|    ($\text{Comp}$)       | Coverage Checker      | architectural dimensions.                       |
|                          |                       | Target: $8 / 8$ ($100.0\%$).                    |
+--------------------------+-----------------------+-------------------------------------------------+
| 5. Comprehension Gain    | Human Subject Pre/Post| $\Delta \text{Score} = \text{Score}_{\text{post}}|
|    ($\Delta C$)          | Standardized Quiz     | - \text{Score}_{\text{pre}}$ (5 questions/task).|
|                          |                       | Target: $\Delta C \ge +35.0\%$.                 |
+--------------------------+-----------------------+-------------------------------------------------+
| 6. Cognitive Load (TLX)  | NASA-TLX Survey       | Raw NASA-TLX weighted score across Mental,      |
|                          |                       | Temporal, Performance, and Frustration scales.  |
|                          |                       | Target: $\ge 40\%$ reduction vs baseline.       |
+--------------------------+-----------------------+-------------------------------------------------+
| 7. User Trust & Clarity  | 5-Point Likert Scale  | Standardized post-study survey across perceived |
|                          | Questionnaire         | clarity, operational trust, and utility.        |
|                          |                       | Target: Mean $\ge 4.2 / 5.0$.                   |
+--------------------------+-----------------------+-------------------------------------------------+
```

---

## 3. Automated Verification Protocol

Automated metrics are computed continuously as part of the Component 4 CI regression test suite (`tests/test_post_delivery_xai.py`):

### 3.1 Traceability & Anti-Hallucination Oracle
For every generated post-delivery explanation, the automated evaluator runs the following verification pipeline:
1. Parse delivered source code into Python `ast.Module`.
2. Extract ground-truth symbol table $S = \{f_1, \dots, f_n\}$ representing all defined functions, classes, and parameters.
3. Extract all symbol mentions $M$ within the synthesized `PostDeliveryExplanation`.
4. Calculate Hallucination Count:
   $$\text{Hallucinations} = |\{m \in M \mid m \notin S \land m \notin \text{Builtins}\}|$$
5. Any explanation yielding $\text{Hallucinations} > 0$ triggers an immediate test assertion failure.

### 3.2 Secrets Sanitization Oracle
Before any explanation is serialized to the response schema:
1. Regex pattern detectors scan all textual fields for credentials patterns:
   - AWS Key IDs (`AKIA[0-9A-Z]{16}`)
   - RSA/EC Private Keys (`-----BEGIN [A-Z ]*PRIVATE KEY-----`)
   - Bearer/JWT tokens (`Bearer eyJ[A-Za-z0-9_-]+\.[A-Za-z0-9_-]+`)
   - Hardcoded password strings (`password\s*=\s*['"][^'"]+['"]`)
2. Explanations must verify $0$ unredacted sensitive tokens, ensuring total leakage prevention.

---

## 4. Human Subject Evaluation Protocol

### 4.1 Participant Cohorts
The study recruits $N = 60$ participants partitioned into two distinct demographic cohorts:

```
+------------------------------------------------------------------------------------+
|                               PARTICIPANT COHORTS                                  |
+-----------------------+---------+--------------------------------------------------+
| Cohort                | Sample  | Profile & Eligibility Criteria                   |
+-----------------------+---------+--------------------------------------------------+
| Cohort A: Engineers   | $n = 30$| Software engineers, systems reviewers, DevOps.   |
| (Technical View)      |         | $\ge 2$ years professional Python experience.    |
| Cohort B: Non-Engineers| $n = 30$| Product managers, business analysts, students.   |
| (Beginner View)       |         | Minimal/no prior programming experience.         |
+-----------------------+---------+--------------------------------------------------+
```

### 4.2 Experimental Design (Between-Subjects & Within-Subjects)
The experiment evaluates participants across 10 delivered software scenarios selected from the Phase 3 100-scenario benchmark:
- **Condition 1 (Control / Baseline)**: Participants receive only the raw source code, docstrings, and execution pass status.
- **Condition 2 (Legacy XAI / Intermediate Logs)**: Participants receive raw test outputs, failure stack traces, and intermediate repair logs.
- **Condition 3 (Proposed Post-Delivery XAI)**: Participants receive the gated post-delivery code understanding package (Cohort A evaluates `TechnicalExplanation`; Cohort B evaluates `BeginnerExplanation`).

### 4.3 Task Flow & Protocol Steps

```
[Step 1: Onboarding]
       | Briefing on task context; demographic questionnaire.
       v
[Step 2: Pre-Explanation Assessment]
       | Participant inspects basic problem specification.
       | Completes 2-question baseline familiarity check.
       v
[Step 3: Explanation Exposure]
       | Participant is assigned to Condition (Control, Legacy, or Post-Delivery).
       | Time-to-comprehension (seconds) is recorded.
       v
[Step 4: Objective Comprehension Quiz]
       | 5 multiple-choice questions per scenario covering:
       | Q1: Software Purpose & Boundaries (Overview)
       | Q2: Data Flow & In/Out Shapes (API & Data-Flow)
       | Q3: Function Role & Behavior (Module Responsibilities)
       | Q4: Algorithmic Logic & Edge Cases (Algorithms & Decisions)
       | Q5: Safe Execution & Dependencies (Setup & Usage)
       v
[Step 5: Subjective Cognitive Load & Trust Survey]
       | NASA-TLX 6-dimension evaluation.
       | 5-point Likert scale (Clarity, Trust, Relevance, Navigation).
```

### 4.4 Standardized Likert Survey Instrument

Participants rate the following statements on a 1 (Strongly Disagree) to 5 (Strongly Agree) Likert scale:

| Item Code | Survey Statement | Measured Construct |
|:---|:---|:---|
| **L-CLR1** | "The explanation clearly described what the delivered software does without confusing terminology." | Perceived Clarity |
| **L-STR1** | "The breakdown of modules and functions accurately reflected the actual structure of the code." | Structural Fidelity |
| **L-TST1** | "Having read this explanation, I feel confident running and deploying this software in a real environment." | Operational Trust |
| **L-USG1** | "The setup instructions and usage examples allowed me to understand how to execute the code immediately." | Actionability |
| **L-COG1** | "I felt overwhelmed by technical jargon or extraneous error logs." *(Reverse Coded)* | Cognitive Friction |
| **L-PRC1** | "The explanation provided the right amount of detail for my technical background." | Dual-Level Calibration |

---

## 5. Statistical Analysis Plan

1. **Comprehension Quiz Differences**:
   - Compute mean comprehension accuracy for each condition.
   - Perform two-way ANOVA (Condition $\times$ Cohort) followed by Tukey's Honest Significant Difference (HSD) post-hoc test to verify significance ($p < 0.05$).
2. **Cognitive Load (NASA-TLX)**:
   - Calculate Wilcoxon signed-rank and Mann-Whitney U tests comparing raw TLX scores across Condition 2 (Intermediate) vs Condition 3 (Post-Delivery).
3. **Traceability & Hallucination Auditing**:
   - Report exact 95% Clopper-Pearson binomial confidence intervals for $\text{Acc}_{\text{XAI}}$ and $\text{Halluc}$.

---

## 6. Ethical Considerations & University Compliance

- **Informed Consent**: All human study participants sign informed consent forms detailing study objectives, voluntary participation, and data anonymization.
- **Data Privacy**: No personally identifiable information (PII) is gathered; responses are indexed via random anonymous participant IDs (`P-01` through `P-60`).
- **Research Integrity**: Benchmark test results, evaluation logs, and participant responses are committed to version control with SHA-256 integrity checksums, prohibiting retrospective modification.
