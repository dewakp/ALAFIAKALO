# ── Stage 1: Build ──
FROM node:20-alpine AS builder

WORKDIR /app

COPY package.json package-lock.json* ./
RUN npm ci

COPY . .
RUN npm run build

# ── Stage 2: Production ──
FROM nginx:1.27-alpine

# Copy built assets.
# `chmod -R a+rX` because COPY preserves the source file mode: a checked-in asset
# that is mode 600 on the developer's machine lands in the image unreadable by
# the `nginx` worker user and is served as 403. That is how /fonts/inter.css
# silently stopped loading — in production as well as locally.
COPY --from=builder /app/dist /usr/share/nginx/html
RUN chmod -R a+rX /usr/share/nginx/html

# SPA fallback + API proxy config
COPY nginx.conf /etc/nginx/conf.d/default.conf

EXPOSE 80

# 127.0.0.1, not localhost: inside the container `localhost` resolves to ::1
# first, and nginx.conf only has `listen 80;` (IPv4). The site was serving fine
# while the healthcheck reported "connection refused" and the container sat
# permanently `unhealthy` — which also blocks any depends_on: service_healthy.
HEALTHCHECK --interval=30s --timeout=3s CMD wget -qO- http://127.0.0.1/health || exit 1

CMD ["nginx", "-g", "daemon off;"]
