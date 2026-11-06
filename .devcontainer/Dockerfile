# syntax=docker/dockerfile:1

FROM mcr.microsoft.com/devcontainers/python:3.15-bookworm
ARG TARGETARCH

RUN apt-get update \
    && apt-get install -y --no-install-recommends ffmpeg libturbojpeg0 libpcap0.8 \
    && apt-get clean

RUN curl --fail --location --retry 3 \
    "https://github.com/AlexxIT/go2rtc/releases/download/v1.9.14/go2rtc_linux_${TARGETARCH}" \
    --output /usr/local/bin/go2rtc \
    && chmod 755 /usr/local/bin/go2rtc

COPY --from=ghcr.io/astral-sh/uv:latest /uv /uvx /usr/local/bin/

ENV UV_LINK_MODE=copy \
    UV_COMPILE_BYTECODE=1 \
    UV_CACHE_DIR=/home/vscode/.cache/uv \
    UV_PROJECT_ENVIRONMENT=/home/vscode/.venv \
    PATH="/home/vscode/.venv/bin:${PATH}"