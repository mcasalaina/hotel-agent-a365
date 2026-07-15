FROM mcr.microsoft.com/entra-sdk/auth-sidecar@sha256:495ec1a7142b3e016b7d9b96ca73cfc6bb504f1c6b4ce07647dd5723275b1b7b AS auth-sidecar

FROM python:3.13-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

RUN apt-get update \
    && apt-get install --yes --no-install-recommends git ca-certificates \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /workspace

COPY --from=auth-sidecar /usr/share/dotnet /usr/share/dotnet
COPY --from=auth-sidecar /app /opt/entra-auth-sidecar
COPY evaluation/assert/ evaluation/assert/
COPY scripts/bootstrap_assert.py scripts/bootstrap_assert.py
COPY scripts/run_assert_evaluation.py scripts/run_assert_evaluation.py
COPY scripts/run_assert_composite.py scripts/run_assert_composite.py

RUN python scripts/bootstrap_assert.py --install \
    && rm -rf evaluation/assert/.runtime/source/.git

ENV DOTNET_ROOT=/usr/share/dotnet \
    DOTNET_RUNNING_IN_CONTAINER=true \
    DOTNET_SYSTEM_GLOBALIZATION_INVARIANT=true

ENTRYPOINT ["python", "scripts/run_assert_composite.py"]
CMD ["validate"]
