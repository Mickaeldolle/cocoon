FROM node:22-alpine AS web-build
WORKDIR /workspace/apps/mobile
COPY apps/mobile/package.json apps/mobile/package-lock.json ./
RUN npm ci
COPY apps/mobile/ ./
ENV EXPO_PUBLIC_API_URL=same-origin
RUN npm run build:web

FROM caddy:2.8-alpine
COPY docker/Caddyfile /etc/caddy/Caddyfile
COPY --from=web-build /workspace/apps/mobile/dist /srv/cocoon
