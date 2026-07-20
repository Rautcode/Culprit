# Culprit web UI — build step 9 (SPEC_VERSION.md).
# Multi-stage: full toolchain to build, standalone bundle to run.

FROM node:22-alpine AS build
WORKDIR /app
COPY package.json package-lock.json ./
RUN npm ci
COPY . .
RUN npm run build

FROM node:22-alpine AS run
WORKDIR /app
ENV NODE_ENV=production
# Non-root with a NUMERIC uid, per the platform's own Kyverno guardrails
# (docs/09-infrastructure.md) — runAsNonRoot verification needs a numeric
# user; a named user fails kubelet's check (CreateContainerConfigError).
RUN addgroup -S -g 10001 culprit && adduser -S -u 10001 -G culprit culprit
COPY --from=build --chown=culprit:culprit /app/.next/standalone ./
COPY --from=build --chown=culprit:culprit /app/.next/static ./.next/static
COPY --from=build --chown=culprit:culprit /app/public ./public
USER culprit
EXPOSE 3000
ENV PORT=3000 HOSTNAME=0.0.0.0
CMD ["node", "server.js"]
