# Use to avoid pull rate limit for Docker Hub images
ARG DOCKER_REGISTRY=docker.io/
FROM ${DOCKER_REGISTRY}library/python:3.11

RUN pip install poetry==1.4.2

COPY . /usr/src/waldur-grafana-sync

WORKDIR /usr/src/waldur-grafana-sync
RUN /bin/true\
    && /usr/bin/poetry config virtualenvs.create false \
    && poetry install --no-interaction \
    && rm -rf /root/.cache/pypoetry

CMD [ "python", "waldur-grafana-sync/main.py" ]
