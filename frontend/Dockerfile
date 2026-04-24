# Vigil frontend — Next.js 16 production build
#
# Multi-stage build to keep the runtime image small:
#   1. deps   — install pnpm dependencies (cached layer)
#   2. build  — `pnpm build` produces the .next/ production artefacts
#   3. runner — minimal image that runs `next start` on :3000
#
# Used by the AWS EC2 docker-compose deploy (see deploy/aws/).
# Frontend is NOT deployed to Render (we use Vercel there); this Dockerfile
# only matters for the all-in-one single-host deploy.

# -----------------------------------------------------------------------------
# 1. deps — install deps against the lockfile
# -----------------------------------------------------------------------------
FROM node:22-alpine AS deps
WORKDIR /app

# pnpm via corepack (pinned to the lockfile's engine range)
RUN corepack enable && corepack prepare pnpm@latest --activate

# Manifest + lockfile first for layer caching
COPY package.json pnpm-lock.yaml pnpm-workspace.yaml ./
RUN pnpm install --frozen-lockfile --prod=false

# -----------------------------------------------------------------------------
# 2. build — compile Next.js production bundle
# -----------------------------------------------------------------------------
FROM node:22-alpine AS build
WORKDIR /app
RUN corepack enable && corepack prepare pnpm@latest --activate

COPY --from=deps /app/node_modules ./node_modules
COPY . .

# Build args surface to build-time as NEXT_PUBLIC_* so they get inlined.
# Leave empty (same-origin) when Caddy proxies /api → api service.
ARG NEXT_PUBLIC_API_BASE_URL=""
ENV NEXT_PUBLIC_API_BASE_URL=$NEXT_PUBLIC_API_BASE_URL

RUN pnpm build

# -----------------------------------------------------------------------------
# 3. runner — runtime image
# -----------------------------------------------------------------------------
FROM node:22-alpine AS runner
WORKDIR /app
ENV NODE_ENV=production
# Next.js 16 reads HOSTNAME + PORT from env natively. Passing them as
# CLI args via `pnpm start -- --hostname ...` breaks: next start treats
# the first positional arg as a project directory, so the old command
# errored with `no such directory: /app/--hostname`.
ENV HOSTNAME=0.0.0.0
ENV PORT=3000

RUN corepack enable && corepack prepare pnpm@latest --activate

# Drop privileges
RUN addgroup -S nodejs && adduser -S nextjs -G nodejs

COPY --from=build --chown=nextjs:nodejs /app/.next ./.next
COPY --from=build --chown=nextjs:nodejs /app/public ./public
COPY --from=build --chown=nextjs:nodejs /app/node_modules ./node_modules
COPY --from=build --chown=nextjs:nodejs /app/package.json ./package.json
COPY --from=build --chown=nextjs:nodejs /app/next.config.ts ./next.config.ts

USER nextjs
EXPOSE 3000

CMD ["pnpm", "start"]
