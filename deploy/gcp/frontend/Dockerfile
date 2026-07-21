# Production frontend image for Cloud Run: build the SPA, then serve it via nginx
# with the reverse-proxy template. Build context is WEB/frontend (see deploy.sh),
# and this Dockerfile is passed with -f. BACKEND_HOST + PORT are injected at run
# time by nginx's envsubst-on-templates entrypoint.
#
# ── Stage 1: build the SPA ──
FROM node:20-alpine AS builder
WORKDIR /app
COPY package.json package-lock.json* ./
RUN npm ci
COPY . .
RUN npm run build

# ── Stage 2: nginx ──
FROM nginx:1.27-alpine
# Remove the default site; our template becomes the active config after envsubst.
RUN rm -f /etc/nginx/conf.d/default.conf
COPY --from=builder /app/dist /usr/share/nginx/html
# nginx:alpine renders /etc/nginx/templates/*.template → /etc/nginx/conf.d/ on boot,
# substituting ${BACKEND_HOST} and ${PORT} from the environment.
COPY deploy-nginx.conf.template /etc/nginx/templates/default.conf.template
ENV PORT=8080
EXPOSE 8080
