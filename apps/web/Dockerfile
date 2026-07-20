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
# Non-root, per the platform's own Kyverno guardrails (docs/09-infrastructure.md).
RUN addgroup -S culprit && adduser -S culprit -G culprit
COPY --from=build --chown=culprit:culprit /app/.next/standalone ./
COPY --from=build --chown=culprit:culprit /app/.next/static ./.next/static
COPY --from=build --chown=culprit:culprit /app/public ./public
USER culprit
EXPOSE 3000
ENV PORT=3000 HOSTNAME=0.0.0.0
CMD ["node", "server.js"]
