# Isolated runtime for manifest-bound generated Task Management workspaces.
# Generated code is mounted at preview time and is not included in this image.

FROM node:20-bookworm-slim

RUN apt-get update \
    && apt-get install -y --no-install-recommends curl socat ca-certificates \
    && rm -rf /var/lib/apt/lists/* \
    && groupadd -r preview && useradd -r -g preview -d /home/preview preview \
    && mkdir -p /home/preview /workspace-ro \
    && chown -R preview:preview /home/preview

COPY entrypoint.sh /usr/local/bin/preview-entrypoint.sh
COPY preview-backend-proxy.mjs /usr/local/lib/intelise-c3/preview-backend-proxy.mjs
RUN chmod 755 /usr/local/bin/preview-entrypoint.sh \
    && chmod 644 /usr/local/lib/intelise-c3/preview-backend-proxy.mjs

USER preview
WORKDIR /tmp

ENV CORS_ALLOWED_ORIGIN=http://127.0.0.1:5180 \
    FRONTEND_PORT=5180 \
    BACKEND_PORT=3001 \
    NPM_CONFIG_CACHE=/tmp/npm-cache \
    NODE_ENV=production

EXPOSE 3001 5180

ENTRYPOINT ["/usr/local/bin/preview-entrypoint.sh"]
