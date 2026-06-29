FROM ghcr.io/astral-sh/uv:python3.14-bookworm-slim AS builder

RUN apt-get update && apt-get install -y --no-install-recommends \
        gcc g++ make wget ca-certificates \
    && wget -q https://sourceforge.net/projects/ta-lib/files/ta-lib/0.4.0/ta-lib-0.4.0-src.tar.gz \
    && tar -xzf ta-lib-0.4.0-src.tar.gz \
    && cd ta-lib && ./configure --prefix=/usr && make -j"$(nproc)" && make install \
    && cd / && rm -rf ta-lib ta-lib-0.4.0-src.tar.gz /var/lib/apt/lists/*

WORKDIR /app

ENV UV_COMPILE_BYTECODE=1
ENV UV_LINK_MODE=copy

COPY pyproject.toml uv.lock ./
RUN uv sync --frozen --no-dev --no-install-project

COPY server.py ./
COPY tools/ ./tools/


FROM python:3.14-slim-bookworm

COPY --from=builder /usr/lib/libta_lib.so* /usr/lib/
RUN ldconfig

COPY --from=builder /app/.venv /app/.venv
COPY --from=builder /app/server.py /app/
COPY --from=builder /app/tools /app/tools

WORKDIR /app

ENV PATH="/app/.venv/bin:$PATH"
ENV HOST=0.0.0.0
ENV PORT=8000

EXPOSE 8000

CMD ["mcp", "run", "server.py", "--transport", "streamable-http", "--host", "0.0.0.0", "--port", "8000"]
