# Blinded Human Evaluation Protocol: Scoped vs. Generic XAI (SO6, RQ4)

## 1. Objective and Research Context
This protocol defines the formal, reproducible methodology for evaluating the technical usefulness of Component 4's Scoped Explainable AI (XAI) diagnostics compared to Generic LLM explanations (Proposal Objective SO6, Research Question RQ4).

In compliance with academic research integrity standards:
- **No synthetic survey participants or fabricated ratings are generated.**
- This protocol establishes the controlled, blinded experimental procedure, participant criteria, evaluation rubric, and statistical analysis plan for execution during dissertation human trials under university ethical oversight.

---

## 2. Experimental Design
The evaluation is conducted as a **within-subjects, double-blind randomized trial**:
1. **Double-Blind Procedure**:
   - Participants are presented with code submissions, defect symptoms, and two diagnostic explanations labeled as **Diagnostic Artifact A** and **Diagnostic Artifact B**.
   - The assignment of Scoped XAI (Component 4) vs. Generic LLM Output (unconstrained base prompt) to Artifact A or B is randomized per scenario.
   - Neither the participant nor the study administrator administering the session knows which artifact corresponds to Component 4.
2. **Scenario Selection**:
   - 10 representative defect scenarios selected from the benchmark dataset across:
     - 3 Functional Bugs (off-by-one, boundary exception, NoneType logic error)
     - 3 Security Vulnerabilities (CWE-89 SQLi, CWE-78 Command Injection, CWE-22 Path Traversal)
     - 2 Performance Bottlenecks (unmemoized recursion, quadratic string concatenation)
     - 2 Regression Defects (re-introduced calculation failure)

---

## 3. Participant Selection & Qualification Criteria
- **Target Sample Size**: $N = 20$ software engineers and computer science researchers.
- **Inclusion Criteria**:
  - Minimum of 2 years professional software development experience OR post-graduate study in software engineering.
  - Demonstrated proficiency in Python debugging and unit test interpretation.
  - Familiarity with CI/CD automated testing concepts.
- **Exclusion Criteria**:
  - Direct contributors to the INTELISE project or Component 4 codebase.
  - Individuals with prior exposure to the benchmark scenario dataset.

---

## 4. Evaluation Rubric (5-Point Likert Scale)

For each diagnostic artifact, participants rate four dimensions from 1 (Strongly Disagree / Unacceptable) to 5 (Strongly Agree / Optimal):

| Dimension | Description | Rating Criteria (1 to 5) |
| :--- | :--- | :--- |
| **D1: Fault Localization Clarity** | Does the explanation clearly and unambiguously identify the exact line and defect symptom? | **1**: Misleading or no line localization.<br>**3**: Correct function but ambiguous line.<br>**5**: Exact line localized with precise runtime failure context. |
| **D2: Diagnostic Groundedness** | Is the explanation strictly grounded in empirical execution evidence without speculation? | **1**: Hallucinated variables or fabricated test results.<br>**3**: Mostly accurate with speculative root cause.<br>**5**: 100% grounded in verified test trace and contract diff. |
| **D3: Repair Actionability** | Does the diagnostic provide actionable guidance for fixing the defect without manual research? | **1**: Vague advice ("fix your code").<br>**3**: General fix direction.<br>**5**: Concrete, minimal repair steps preserving contract integrity. |
| **D4: Technical Trustworthiness** | Would you trust this diagnostic in an automated, unattended CI/CD deployment pipeline? | **1**: Would immediately disable automated feedback.<br>**3**: Requires mandatory human double-check.<br>**5**: High confidence; ready for automated agent consumption. |

---

## 5. Statistical Analysis Methodology
1. **Primary Hypothesis ($H_1$)**:
   $$\mu_{\text{Scoped XAI}} > \mu_{\text{Generic XAI}} \quad \text{with } p < 0.01$$
2. **Statistical Test**:
   - Two-tailed Wilcoxon Signed-Rank Test for paired ordinal data across all 4 rubric dimensions.
   - Effect size calculated using Cliff's Delta ($\delta$) for non-parametric ordinal distributions.
3. **Inter-Rater Reliability (IRR)**:
   - Evaluated using Fleiss' Kappa ($\kappa$) across participant ratings.
   - Target agreement threshold: $\kappa \ge 0.65$ (substantial agreement).

---

## 6. Execution Status & Ethical Governance
- **Current Status**: Formal protocol frozen; human trials scheduled upon university institutional ethics clearance.
- **Reporting Rule**: Literature constants (e.g. 2.4/5.0 from Joshi et al., 2026) are cited solely as reference benchmarks and MUST NOT be presented as measured experimental data of this cohort.
