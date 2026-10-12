# syntax=docker/dockerfile:1

FROM mcr.microsoft.com/devcontainers/python:3.14-bookworm

RUN apt-get update \
    && apt-get install -y --no-install-recommends ffmpeg libturbojpeg0 \
    && rm -rf /var/lib/apt/lists/*

COPY --from=ghcr.io/astral-sh/uv:latest /uv /uvx /usr/local/bin/

ENV UV_LINK_MODE=copy \
    UV_COMPILE_BYTECODE=1 \
    UV_CACHE_DIR=/home/vscode/.cache/uv \
    UV_PROJECT_ENVIRONMENT=/home/vscode/.venv \
    PATH="/home/vscode/.venv/bin:${PATH}"