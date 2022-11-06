# Use to avoid pull rate limit for Docker Hub images
ARG DOCKER_REGISTRY=docker.io/
FROM ${DOCKER_REGISTRY}library/python:3.9

COPY . /usr/src/waldur-grafana-sync

WORKDIR /usr/src/waldur-grafana-sync
RUN pip install -r requirements.txt --no-cache-dir

CMD [ "python", "main.py" ]
