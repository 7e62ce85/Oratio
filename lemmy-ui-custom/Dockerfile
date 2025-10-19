FROM node:alpine as builder

# Added vips-dev and pkgconfig so that local vips is used instead of prebuilt
# Done for two reasons:
# - libvips binaries are not available for ARM32
# - It can break depending on the CPU (https://github.com/LemmyNet/lemmy-ui/issues/1566)
RUN apk update && apk upgrade && apk add --no-cache curl python3 build-base gcc wget git vips-dev pkgconfig

# Enable corepack to use pnpm (check if corepack exists first)
RUN if command -v corepack >/dev/null 2>&1; then corepack enable; else npm install -g pnpm; fi

# Install node-gyp
RUN npm install -g node-gyp

WORKDIR /usr/src/app

ENV npm_config_target_platform=linux
ENV npm_config_target_libc=musl

# Build-time arguments for environment variables
ARG LEMMY_API_KEY
ARG LEMMY_BCH_API_URL
ARG LEMMY_BCH_PAYMENT_URL
ARG COMMIT_HASH

# Convert build args to environment variables for webpack
ENV LEMMY_API_KEY=${LEMMY_API_KEY}
ENV LEMMY_BCH_API_URL=${LEMMY_BCH_API_URL}
ENV LEMMY_BCH_PAYMENT_URL=${LEMMY_BCH_PAYMENT_URL}
ENV COMMIT_HASH=${COMMIT_HASH}

# Cache deps
COPY package.json pnpm-lock.yaml ./
RUN pnpm i
# Build
COPY generate_translations.js \
  tsconfig.json \
  webpack.config.js \
  .babelrc \
  ./

COPY lemmy-translations lemmy-translations
COPY src src
COPY public public
# COPY .git .git

# # Set UI version 
RUN mkdir -p .git &&     echo "export const VERSION = 'v0.19.8-custom';" > "src/shared/version.ts"

RUN pnpm i
RUN pnpm prebuild:prod
RUN pnpm build:prod

# remove unneeded deps
RUN rm -rf ./node_modules/import-sort-parser-typescript
RUN rm -rf ./node_modules/typescript
RUN rm -rf ./node_modules/npm

# The runner stage
FROM node:alpine as runner
ENV NODE_ENV=production

# Runtime environment variables for BCH integration
ARG LEMMY_API_KEY
ARG LEMMY_BCH_API_URL
ARG LEMMY_BCH_PAYMENT_URL
ARG COMMIT_HASH

ENV LEMMY_API_KEY=${LEMMY_API_KEY}
ENV LEMMY_BCH_API_URL=${LEMMY_BCH_API_URL}
ENV LEMMY_BCH_PAYMENT_URL=${LEMMY_BCH_PAYMENT_URL}
ENV COMMIT_HASH=${COMMIT_HASH}

RUN apk update && apk add --no-cache curl vips-cpp && rm -rf /var/cache/apk/*

COPY --from=builder /usr/src/app/dist /app/dist
COPY --from=builder /usr/src/app/node_modules /app/node_modules
COPY --from=builder /usr/src/app/public /app/public

RUN chown -R node:node /app

LABEL org.opencontainers.image.authors="The Lemmy Authors"
LABEL org.opencontainers.image.source="https://github.com/LemmyNet/lemmy-ui"
LABEL org.opencontainers.image.licenses="AGPL-3.0-or-later"
LABEL org.opencontainers.image.description="The official web app for Lemmy."

HEALTHCHECK --interval=60s --start-period=10s --retries=2 --timeout=10s CMD curl -ILfSs http://localhost:1234/ > /dev/null || exit 1

USER node
EXPOSE 1234
WORKDIR /app

CMD ["node", "dist/js/server.js"]
