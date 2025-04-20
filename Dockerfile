# syntax=docker/dockerfile:1.5
########################################
# 1) Build stage – install deps with uv
########################################
FROM ghcr.io/astral-sh/uv:python3.12-bookworm-slim AS builder

WORKDIR /app

ENV UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy

# 의존성 레이어 캐싱
COPY pyproject.toml uv.lock* ./
RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --frozen --no-install-project --no-dev --no-editable

# 소스 코드 추가 후 프로젝트 설치
COPY . .
RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --frozen --no-dev --no-editable

########################################
# 2) Final stage – runtime
########################################
FROM python:3.12-slim-bookworm

# 비루트 사용자
RUN useradd --create-home app
WORKDIR /app

# 1) 가상환경 + 패키지
COPY --from=builder --chown=app:app /app/.venv /app/.venv
# 2) 소스 코드
COPY --from=builder --chown=app:app /app /app
# 3) uv 실행 파일
COPY --from=builder /usr/local/bin/uv /usr/local/bin/uv

# PATH: .venv > uv > 기본
ENV PATH="/app/.venv/bin:${PATH}" \
    PYTHONUNBUFFERED=1

USER app

# uv run으로 FastMCP 실행 (stdio 모드)
ENTRYPOINT ["uv", "run", "--venv", "/app/.venv", "dart.py"]
