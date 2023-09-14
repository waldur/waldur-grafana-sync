# Use to avoid pull rate limit for Docker Hub images
ARG DOCKER_REGISTRY=docker.io/
FROM ${DOCKER_REGISTRY}library/python:3.11

RUN pip install poetry==1.4.2

ENV POETRY_NO_INTERACTION=1 \
    POETRY_VIRTUALENVS_IN_PROJECT=1 \
    POETRY_VIRTUALENVS_CREATE=1 \
    POETRY_CACHE_DIR=/tmp/poetry_cache

COPY . /usr/src/waldur-grafana-sync

WORKDIR /usr/src/waldur-grafana-sync
RUN --mount=type=cache,target=$POETRY_CACHE_DIR poetry install --without dev --no-root

CMD [ "python", "waldur-grafana-sync/main.py" ]
