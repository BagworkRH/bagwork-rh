# bagworkRH frontend image — Next.js, built in one stage and run lean in another.
#
# NEXT_PUBLIC_* variables are inlined into the client bundle at BUILD time; they
# are not read at runtime. Setting NEXT_PUBLIC_API_URL only on `docker run`
# would therefore do nothing — the browser would keep whatever the build saw.
# That is why it is an ARG here and a build arg in compose; changing it means
# rebuilding the image, not restarting the container.
FROM node:20-slim AS build
WORKDIR /app
ENV NEXT_TELEMETRY_DISABLED=1

ARG NEXT_PUBLIC_API_URL
ENV NEXT_PUBLIC_API_URL=${NEXT_PUBLIC_API_URL}

COPY package.json package-lock.json ./
RUN npm ci

COPY . .
RUN npm run build

# Runner: the compiled output plus production dependencies only, so the shipped
# image carries no build toolchain.
FROM node:20-slim AS runner
WORKDIR /app
ENV NODE_ENV=production \
    NEXT_TELEMETRY_DISABLED=1

COPY package.json package-lock.json ./
RUN npm ci --omit=dev && npm cache clean --force

COPY --from=build /app/.next ./.next
COPY --from=build /app/public ./public

# The base image ships an unprivileged `node` user; the app binds 3000.
USER node
EXPOSE 3000
CMD ["npm", "run", "start"]
