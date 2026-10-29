# syntax=docker/dockerfile:1

ARG NODE_IMAGE=node:24-bookworm-slim@sha256:a5f4366e834695d5f363b920c104953a535d3a9864d1bdf74566a0ebe01daee5

FROM ${NODE_IMAGE} AS frontend-validation
ARG APP_PATH
ARG VITE_API_BASE_URL=http://127.0.0.1:3001
USER root
RUN install -d -o node -g node /validation/frontend
USER node
WORKDIR /validation/frontend
COPY --chown=node:node ${APP_PATH}/frontend/package.json ./package.json
RUN npm config set registry https://registry.npmjs.org/ \
    && npm install --ignore-scripts --no-audit --no-fund \
    && npm audit --audit-level=high
COPY --chown=node:node ${APP_PATH}/frontend/ ./
ENV VITE_API_BASE_URL=${VITE_API_BASE_URL}
RUN npm run build

FROM ${NODE_IMAGE} AS backend-validation
ARG APP_PATH
USER root
RUN install -d -o node -g node /validation/backend
USER node
WORKDIR /validation/backend
COPY --chown=node:node ${APP_PATH}/backend/package.json ./package.json
RUN npm config set registry https://registry.npmjs.org/ \
    && npm install --ignore-scripts --no-audit --no-fund \
    && npm audit --audit-level=high
COPY --chown=node:node ${APP_PATH}/backend/ ./
RUN npm test \
    && npm prune --omit=dev --ignore-scripts \
    && npm cache clean --force

FROM ${NODE_IMAGE} AS runtime
ARG CORS_ALLOWED_ORIGIN=http://127.0.0.1:5173
ENV NODE_ENV=production \
    HOST=127.0.0.1 \
    PORT=3001 \
    CORS_ALLOWED_ORIGIN=${CORS_ALLOWED_ORIGIN}
WORKDIR /app
COPY --from=backend-validation --chown=node:node /validation/backend ./backend
COPY --from=frontend-validation --chown=node:node /validation/frontend/dist ./frontend-dist
COPY --chown=node:node harness/api-smoke.mjs /opt/intelise-validator/api-smoke.mjs
COPY --chown=node:node harness/static-server.mjs /opt/intelise-validator/static-server.mjs
USER node
EXPOSE 3001 8080
CMD ["node", "backend/src/app.js"]

FROM runtime AS preview
COPY --chown=node:node harness/preview-entry.mjs /opt/intelise-validator/preview-entry.mjs
ENV BACKEND_HOST=0.0.0.0 \
    STATIC_HOST=0.0.0.0 \
    STATIC_PORT=8080
CMD ["node", "/opt/intelise-validator/preview-entry.mjs"]


