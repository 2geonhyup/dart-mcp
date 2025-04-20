# syntax=docker/dockerfile:1.5
########################################
# 1) Build stage – install deps with uv
########################################
FROM ghcr.io/astral-sh/uv:python3.12-bookworm-slim AS builder

WORKDIR /app

#–– 더 빠른 빌드를 위한 설정
ENV UV_COMPILE_BYTECODE=1     \
    UV_LINK_MODE=copy

# pyproject / 잠재적 lockfile 먼저 복사 → deps 전용 레이어 캐시
#(uv.lock 이 아직 없으면 COPY 시 경고만 뜨고 넘어갑니다)
COPY pyproject.toml uv.lock* ./

# 의존성 설치 (프로젝트 코드는 아직 COPY 안함 → 레이어 캐시 최적화)
RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --frozen --no-install-project --no-dev --no-editable

# 이후 실제 소스 추가
COPY . .

# 소스까지 포함해 설치 (–no-dev 로 프로덕션 전용)
RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --frozen --no-dev --no-editable

########################################
# 2) Final stage – 슬림 런타임 이미지
########################################
FROM python:3.12-slim-bookworm

# 안전하게 실행할 비루트 계정
RUN useradd --create-home app
WORKDIR /app

# 가상환경 + 패키지 복사
COPY --from=builder /root/.local        /root/.local
COPY --from=builder /app/.venv          /app/.venv
COPY --from=builder /app                /app

# PATH 맨 앞에 venv bind
ENV PATH="/app/.venv/bin:${PATH}" \
    PYTHONUNBUFFERED=1

# 필요하면 환경변수(DART_API_KEY 등)를 docker run 시 -e 로 넘기세요
# 예) docker run -e DART_API_KEY=xxxxxxxx myimage

USER app

# FastMCP 서버 실행 (stdin/stdout transport)
ENTRYPOINT ["python", "-u", "dart.py"]