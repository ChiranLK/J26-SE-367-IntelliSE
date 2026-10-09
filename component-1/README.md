# Component 01 — Requirement Engineering Agent

AI-Powered Intelligent Requirement Engineering Agent for Agile Software Development.
The component will transform client communications into structured requirements,
classify FR/NFR, identify quality issues, generate Agile artifacts and an SRS,
and support client review and targeted regeneration.

This is foundation work only, not 50% completion toward the proposed
October 18, 2026 prototype deadline. Requirement processing, AI integration,
MongoDB persistence, authentication, and deployment remain unimplemented.

Implementation is maintained in two independent branches from a common base:

- `component-1-backend`: FastAPI service. See `backend/README.md` on that branch.
- `component-1-frontend`: React/Vite page. See `frontend/README.md` on that branch.

Each branch contains only its own implementation and setup guide. Run both
worktrees together to verify the frontend API connection. The backend defaults
to http://127.0.0.1:8001 and the frontend to http://127.0.0.1:5173.
No credentials, local environment files, dependencies, or build output belong
in Git. Other components and shared contracts are unchanged.
