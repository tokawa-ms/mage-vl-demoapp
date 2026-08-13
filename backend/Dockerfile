FROM pytorch/pytorch:2.9.0-cuda12.8-cudnn9-devel@sha256:97ec2a667dd7560c615bf50a95b2fb85a673ae233a55da1706e8e04e6d6d518e

ENV DEBIAN_FRONTEND=noninteractive \
    MAX_JOBS=4 \
    NVCC_THREADS=2 \
    TORCH_CUDA_ARCH_LIST=8.6 \
    PIP_NO_CACHE_DIR=1 \
    PYTHONUNBUFFERED=1

RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    curl \
    ffmpeg \
    git \
    ninja-build \
    pkg-config \
    protobuf-compiler \
    rustc \
    cargo \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

COPY backend/pyproject.toml backend/requirements.lock.txt /app/
RUN pip install --require-hashes --no-build-isolation \
        --requirement requirements.lock.txt \
    && pip install --no-deps -e ".[test]"

COPY backend/app /app/app
COPY backend/tests /app/tests

EXPOSE 8000
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
