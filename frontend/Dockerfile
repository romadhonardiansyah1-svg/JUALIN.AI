# JUALIN.AI Frontend — Dockerfile (Multi-stage)
FROM node:20-alpine AS builder

WORKDIR /app

# Install deps
COPY package.json package-lock.json ./
RUN npm ci --ignore-scripts

# Copy source
COPY . .

# Rewrites are compiled during `next build`, so the internal URL must be set here.
ARG INTERNAL_API_URL=http://backend:8000
ENV INTERNAL_API_URL=${INTERNAL_API_URL}
ENV NEXT_PUBLIC_API_URL=""

# Build
RUN npm run build

# ── Production image ──
FROM node:20-alpine AS runner

WORKDIR /app

ENV NODE_ENV=production
ENV PORT=3000

# Copy built app
COPY --from=builder /app/.next/standalone ./
COPY --from=builder /app/.next/static ./.next/static
COPY --from=builder /app/public ./public

EXPOSE 3000

CMD ["node", "server.js"]
