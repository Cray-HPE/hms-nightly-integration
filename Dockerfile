FROM artifactory.algol60.net/csm-docker/stable/docker.io/library/alpine:3.15

WORKDIR /src

# Install base packages
RUN set -ex \
    && apk -U upgrade \
    && apk add --no-cache \
        python3 \
        python3-dev \
        py3-pip \
        bash \
        curl \
        tar \
        gcc \
        musl-dev \
    && pip3 install --upgrade \
        pip \
        pytest==7.1.2 \
        tavern==1.23.1 \
        allure-pytest==2.12.0 \
    && apk del \
        python3-dev \
        tar \
        gcc \
        musl-dev

COPY tests tests
COPY tavern_global_config.yaml .
COPY smoke smoke