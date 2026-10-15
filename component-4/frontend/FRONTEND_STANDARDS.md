# INTELISE — Frontend Standards & Regression Prevention Guidelines

## 1. Overview & Purpose

This document establishes the permanent product language, user experience standards, visual hierarchy, and regression prevention policies for the INTELISE frontend application (`component-4/frontend/`).

INTELISE is a production-grade software engineering platform designed for:
- Automated code verification and test execution (Python pytest in isolated Docker environments).
- Evidence-based defect analysis synthesized from empirical test failures and tracebacks.
- Human-facing Explainable AI (XAI) root-cause reasoning for software reviewers.
- Structured technical feedback preparation and repair loop integration.

All user interfaces must look, read, and behave like a professional software product rather than an academic research prototype.

---

## 2. Product-Facing Language Policy

### Approved Terminology Reference Table

| Category | Preferred Product Term | Prohibited / Outdated Term |
| :--- | :--- | :--- |
| **Platform Identity** | INTELISE Code Verification & Repair Feedback Platform | INTELISE Component 4 / Research Assistant |
| **System Capabilities** | Automated Code Verification, Defect Analysis | Phase 2, Phase 2B, Phase 2C, Milestone 1 |
| **Test Explanations** | Human-Facing XAI Explanations / Test Explanations | Phase 3 Milestone 1 / Decoupled Research Architecture |
| **Explanations Audience** | Target: Reviewer / Software Engineer | Target: Human Reviewer (Research Subject) |
| **Explanation Provider** | *(Omit internal engine tag or use "Verification Engine")* | Provider: deterministic_evidence_v1 |
| **Repair System** | Repair Service / Repair Integration | Component 3 / C3 |
| **Repair Feedback** | Repair Feedback / Technical Feedback | Component 3 Feedback |
| **Repair Action** | Send for Repair / Return for Repair | Dispatch to C3 / Return to Component 3 |
| **Repair Job** | Repair Job | Component 3 Job |
| **Closed-Loop Iteration** | Repair Feedback Workflow | Bi-Directional Feedback Architecture |
| **Repair Delivery State** | Automatic repair delivery is currently unavailable | Component 3 contract under development |
| **Delivery Status** | Delivery Unavailable / Not Connected | Pending C3 Contract |
| **Testing Oracle** | Verification Standard: Only authorized test specifications determine correctness | Phase 2B requirement: Only explicitly authorized test cases... |
| **Defect Detection** | Evidence-based defect analysis | Phase 2C Active / Phase 2 Architectural Specification |
| **Verification State** | Pending Verification / Awaiting test execution | Phase 2 Queue |
| **Pass Status** | Verified Passing | Zero Fabricated |

### Prohibited Copy Categories

Never introduce the following into user-facing text, JSX elements, labels, buttons, or dialogs:
1. **Phases & Subphases**: `Phase 1`, `Phase 2`, `Phase 2A`, `Phase 2B`, `Phase 2C`, `Phase 3`, `Phase 4`.
2. **Milestones & Roadmaps**: `Milestone 1`, `Milestone 2`, `Milestone 3`, `Roadmap Stage 2`.
3. **Internal Component Numbers**: `Component 1`, `Component 2`, `Component 3`, `Component 4`.
4. **Internal Component Abbreviations**: `C1`, `C2`, `C3`, `C4`.
5. **Academic Disclaimers & Ethics Notes**: `research ethics`, `research architecture`, `academic methodology`, `zero fabricated`.
6. **Developer-Only Schemas**: Dumps of Python Pydantic classes (`class DefectReport(BaseModel)`) or backend modules in normal user views.
7. **Provisional Notices**: "Contract under development in shared repository", "provisional endpoint".
8. **Misleading Statuses**: Describing active features (e.g., test execution or defect analysis) as merely "planned", "simulated", or "unavailable".

> [!NOTE]
> Internal identifiers in code (e.g., API routes `/api/v1/verifications/integrations/component-3/status`, backend database field `component_3_job_id`, or variable `getComponent3Status`) are permitted in internal logic and API communication. They must simply be mapped to professional product labels before rendering in the UI.

---

## 3. Centralized UI Terminology Module

To avoid hardcoded duplicates and text divergence, import standard terminology from:
`src/utils/terminology.js`

```javascript
import { TERMINOLOGY } from '../utils/terminology';

// Example Usage
<h1>{TERMINOLOGY.CODE_VERIFICATION}</h1>
<Badge>{TERMINOLOGY.REPAIR_INTEGRATION}</Badge>
<Button>{TERMINOLOGY.ACTIONS.APPROVE_FOR_REPAIR}</Button>
```

---

## 4. Visual Design System & Aesthetics

All UI components must adhere to the INTELISE Dark Graphite & Orange design system:

### Color Palette Tokens (CSS Variables)
- **Background Root**: `var(--bg-root)` (`#0d0e15`)
- **Card Background**: `var(--bg-card)` (`#14161f`)
- **Input Background**: `var(--bg-input)` (`#0a0b10`)
- **Borders**: `var(--border-color)` (`#222638`), `var(--border-subtle)` (`#1a1d2c`)
- **Primary / Brand Accent**: `var(--primary-500)` (`#f97316`), `var(--primary-400)` (`#fb923c`), `var(--primary-300)` (`#fdba74`)
- **Success / Passed**: `var(--status-passed)` (`#10b981`), `var(--status-passed-bg)` (`rgba(16, 185, 129, 0.1)`)
- **Failure / Danger**: `var(--status-failed)` (`#ef4444`), `var(--status-failed-bg)` (`rgba(239, 68, 68, 0.1)`)
- **Warning / Pending**: `var(--status-pending)` (`#f59e0b`), `var(--status-pending-bg)` (`rgba(245, 158, 11, 0.1)`)
- **Typography**: Inter for UI text; JetBrains Mono for identifiers, stack traces, and code diffs.

### UI Guidelines
- **Cards**: Use `<Card title="..." subtitle="...">` with subtle borders (`1px solid var(--border-color)`). Avoid high-contrast jarring borders.
- **Badges**: Use `<Badge variant="primary|secondary|success|warning|danger|accent" dot?>` with consistent casing.
- **Buttons**: Use `<Button variant="primary|secondary|outline|danger" size="sm|md|lg">`. Include loading indicators when submitting async actions.
- **Spacing**: Use standard 8px grid units (`0.5rem`, `0.75rem`, `1rem`, `1.25rem`, `1.5rem`).
- **No Repeated Banners**: Do not stack multiple notification banners on the same view. Combine operational diagnostics into single clear status cards.

---

## 5. Responsive Layout & Usability Standards

### Desktop, Tablet, and Mobile Support
- **Grid Layouts**: Use responsive auto-fit grids (`grid-template-columns: repeat(auto-fit, minmax(280px, 1fr))`) to prevent cramped columns on medium viewports.
- **No Heading Collisions**: Headings and action buttons must wrap gracefully (`display: flex; flex-wrap: wrap; gap: 0.5rem; justify-content: space-between`).
- **Full Identifiers & Copy Buttons**: Never truncate critical identifiers (Run IDs, Correlation IDs, Job IDs) aggressively in detail views. Provide 1-click clipboard copy buttons with visual feedback (`Check` icon for 2 seconds).
- **Feedback History Cards**: The card-based audit iteration layout must be preserved. Do not revert iteration records into cramped tabular grids.

---

## 6. Accessibility & Operational Rules

1. **Semantic HTML**: Use proper `<header>`, `<nav>`, `<main>`, `<aside>`, `<h1>`-`<h3>`, `<button>`, and `<label>` tags.
2. **Keyboard Accessibility**: Ensure all interactive controls have accessible names, proper `:focus-visible` styles, and keyboard handlers (`onKeyDown` for code editors and search inputs).
3. **Operational Error States**: When the backend is offline or an API request fails, provide a clear, constructive message indicating the exact service and host URL, without developer jargon.
4. **Fail-Closed Safety**: Automatic external repair dispatch remains disabled until a verified external endpoint is connected. Outbound delivery buttons must remain safely disabled (`disabled={!c3Status?.dispatch_allowed}`).

---

## 7. Automated Terminology Regression Checker

### How to Run the Automated Check
Run the automated copy checker at any time via:
```bash
npm run check:ui-copy
```

### What the Checker Inspects
The check inspects all JSX text nodes, user-facing JSX attributes (`title`, `subtitle`, `label`, `description`, `placeholder`, `aria-label`, `alt`), and UI notification messages across `src/pages`, `src/components`, and `src/utils`.

Offending lines are reported with file path, line number, rule identifier, and context snippet. The command exits with code `1` if any violation is detected.

### Inline Exemptions
If a specific line contains a term that is narrowly justified (e.g., historical archive display), add an inline exemption comment:
```jsx
<span>Phase 2 Historical Archive</span> {/* ui-copy-ignore: Historical archive reference */}
```

---

## 8. Pre-Completion Review Checklist for Future Features

Before marking any frontend task complete, verify the following:

- [ ] `npm run check:ui-copy` passes with 0 violations.
- [ ] `npm test` runs and all unit test suites pass (45+ tests).
- [ ] `npm run build` succeeds with zero production build errors.
- [ ] `npm run lint` finishes with zero syntax or fatal lint errors.
- [ ] No phase numbers (`Phase X`), milestones, or internal component numbers (`Component X`, `CX`) appear in rendered text.
- [ ] No research disclaimers or provisional implementation warnings are exposed.
- [ ] Repair integration terminology conforms to `TERMINOLOGY` standards.
- [ ] Responsive layouts behave cleanly on 320px, 768px, 1024px, and 1440px viewports.
- [ ] Feedback History cards remain intact with full copyable correlation and run IDs.
- [ ] Repair dispatch controls remain disabled and fail-closed safety is enforced.
