# INTELISE Component 4 — React.js Frontend (Phase 2A)

> **Component 4: Intelligent Agentic Testing & Feedback Loop Assistant**  
> Modern, responsive React dashboard integrating with the Component 4 FastAPI backend.

---

## Overview

The Component 4 frontend provides an interactive, research-grade dashboard for software engineering researchers to:
- Monitor live backend connectivity, health metrics, and storage engine status (ephemeral in-memory vs. MongoDB Atlas).
- Submit source code manually across 10 programming languages with requirement tags.
- Safely upload source code files with client-side drag-and-drop, extension validation, and 2MB size enforcement.
- Browse paginated submission history, view read-only source code with line numbers, and copy code safely.
- Initiate and monitor verification runs (created in actual backend `PENDING` status).
- Review architectural roadmaps for upcoming Phase 2 defect detection and Phase 3 Explainable AI (XAI) feedback loops.

---

## Tech Stack

- **Framework**: React.js 19 with JSX (ES6+)
- **Build Tool**: Vite 8
- **Routing**: React Router v7 (`react-router-dom`)
- **Icons**: Lucide React (`lucide-react`)
- **HTTP Client**: Axios (`axios`)
- **Styling**: Vanilla Modern CSS (CSS custom properties, glassmorphism, responsive drawer, dark/light themes)
- **Testing**: Vitest, `@testing-library/react`, `@testing-library/jest-dom`, `jsdom`

---

## Project Structure

```text
component-4/frontend/
├── public/
│   └── favicon.svg
├── src/
│   ├── __tests__/                  # Unit and component tests (Vitest)
│   │   ├── apiClient.test.js
│   │   ├── components.test.jsx
│   │   ├── formatters.test.js
│   │   └── pages.test.jsx
│   ├── api/                        # Modular Axios API client
│   │   ├── client.js               # Base client with offline error detection
│   │   ├── healthApi.js            # /health endpoint with latency tracking
│   │   ├── submissionApi.js        # /api/v1/submissions & /upload
│   │   └── verificationApi.js      # /api/v1/verifications & status
│   ├── components/
│   │   ├── common/                 # Reusable UI primitives
│   │   │   ├── Alert.jsx           # Semantic alert banners
│   │   │   ├── Badge.jsx           # Color-coded status tags
│   │   │   ├── Button.jsx          # Button with loading state & icons
│   │   │   ├── Card.jsx            # Card container
│   │   │   ├── CodeViewer.jsx      # Safe text-based code viewer
│   │   │   ├── EmptyState.jsx      # Clean empty state with CTA
│   │   │   ├── LoadingSkeleton.jsx # Skeleton loaders
│   │   │   ├── Modal.jsx           # Accessible modal dialog
│   │   │   ├── Pagination.jsx      # Skip & limit pagination
│   │   │   └── StatCard.jsx        # Metric KPI cards
│   │   └── layout/
│   │       ├── AppLayout.jsx       # Root shell
│   │       ├── Breadcrumbs.jsx     # Route breadcrumbs
│   │       ├── Navbar.jsx          # Live health pill & theme switch
│   │       └── Sidebar.jsx         # Responsive sidebar & drawer
│   ├── pages/
│   │   ├── DashboardPage.jsx       # Live overview and stats
│   │   ├── DefectReportsPage.jsx   # Phase 2 reserved roadmap
│   │   ├── FeedbackHistoryPage.jsx # Phase 3 reserved roadmap
│   │   ├── FileUploadPage.jsx      # Drag-and-drop file upload
│   │   ├── ManualSubmissionPage.jsx# Code editor submission
│   │   ├── SubmissionHistoryPage.jsx # Paginated history
│   │   ├── VerificationRunsPage.jsx# Verification management
│   │   └── XaiExplanationsPage.jsx # Phase 3 reserved roadmap
│   ├── styles/                     # Pure CSS design system
│   │   ├── components.css
│   │   ├── global.css
│   │   ├── layout.css
│   │   └── variables.css
│   ├── utils/
│   │   ├── constants.js            # Enums, statuses, allowed extensions
│   │   └── formatters.js           # Date, byte, and file utilities
│   ├── App.jsx                     # Route definitions
│   ├── main.jsx                    # Application entry point
│   └── setupTests.js               # Vitest environment setup
├── .env.example
├── index.html
├── package.json
└── vite.config.js
```

---

## Installation & Setup

### 1. Prerequisites
- **Node.js**: v18+ (tested on Node.js v24.21.0)
- **npm**: v9+ (tested on npm 11.19.0)

### 2. Install Dependencies
```bash
cd component-4/frontend
npm install
```

### 3. Configure Environment Variables
Create a `.env` file based on `.env.example`:
```bash
cp .env.example .env     # Linux / macOS
copy .env.example .env   # Windows
```

Contents:
```ini
# Base URL of the Component 4 FastAPI backend
VITE_API_BASE_URL=http://127.0.0.1:8000
```

---

## Development & Production Commands

| Command | Description |
|---|---|
| `npm run dev` | Starts Vite local development server on `http://127.0.0.1:5173/` |
| `npm run build` | Compiles production assets into `dist/` |
| `npm run preview` | Previews the production build locally |
| `npm run test` | Runs the Vitest automated test suite |

---

## Running Frontend Tests

Execute the 27 unit and integration tests:

```bash
cd component-4/frontend
npm run test
```

Test coverage includes:
- **API Client**: Error interceptors, network offline handling, query formatting.
- **Components**: Badges, Buttons, StatCards, Modals, Pagination, CodeViewer.
- **Pages**: Form validation, dropzone checks, roadmap banners, empty states.
- **Utilities**: Byte formatting, language detection, extension validation.
