# syntax=docker/dockerfile:1

FROM mcr.microsoft.com/devcontainers/python:3.14-bookworm

COPY --from=ghcr.io/astral-sh/uv:latest /uv /uvx /usr/local/bin/

ENV UV_LINK_MODE=copy \
    UV_COMPILE_BYTECODE=1 \
    UV_CACHE_DIR=/home/vscode/.cache/uv \
    UV_PROJECT_ENVIRONMENT=/home/vscode/.venv