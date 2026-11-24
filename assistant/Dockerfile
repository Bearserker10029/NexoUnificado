# syntax=docker/dockerfile:1
# SPDX-FileCopyrightText: 2026 Kent Lin, Luis Quillas, Jeniffer Castillo
# SPDX-License-Identifier: Apache-2.0
FROM node:26-bookworm AS airi
WORKDIR /airi
ENV CI=true HUSKY=0 SKIP_SIMPLE_GIT_HOOKS=1
RUN git clone --depth 1 --branch v0.15.4 https://github.com/moeru-ai/airi.git . \
    && test "$(git rev-parse HEAD)" = 69d60cf95f13c8a52e763bf3119159739633084f
RUN npm install -g pnpm@11.24.0
RUN --mount=type=cache,target=/root/.local/share/pnpm/store \
    ONNXRUNTIME_NODE_INSTALL_CUDA=skip npm_config_onnxruntime_node_install_cuda=skip \
    pnpm install --frozen-lockfile --fetch-timeout=240000 --fetch-retries=4
COPY airi/configure.mjs /tmp/configure.mjs
RUN --mount=type=cache,target=/airi/.cache node /tmp/configure.mjs \
    && TARGET_HUGGINGFACE_SPACE=true VITE_APP_TARGET_HUGGINGFACE_SPACE=true NODE_OPTIONS=--max-old-space-size=6144 pnpm -F @proj-airi/stage-web run build --base=/airi/stage/

FROM python:3.12-slim
WORKDIR /app
ENV PYTHONUNBUFFERED=1 PYTHONDONTWRITEBYTECODE=1
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY app.py providers.py ./
COPY web ./web
COPY --from=airi /airi/apps/stage-web/dist ./stage
COPY --from=airi /airi/LICENSE ./stage/AIRI-LICENSE.txt
RUN mkdir -p /data && chown 10001:10001 /data
USER 10001:10001
CMD ["gunicorn", "--bind", "0.0.0.0:8000", "--threads", "8", "--timeout", "150", "app:app"]
