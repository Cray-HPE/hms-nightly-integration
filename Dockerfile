# MIT License
#
# (C) Copyright [2023] Hewlett Packard Enterprise Development LP
#
# Permission is hereby granted, free of charge, to any person obtaining a
# copy of this software and associated documentation files (the "Software"),
# to deal in the Software without restriction, including without limitation
# the rights to use, copy, modify, merge, publish, distribute, sublicense,
# and/or sell copies of the Software, and to permit persons to whom the
# Software is furnished to do so, subject to the following conditions:
#
# The above copyright notice and this permission notice shall be included
# in all copies or substantial portions of the Software.
#
# THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
# IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
# FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL
# THE AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR
# OTHER LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE,
# ARISING FROM, OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR
# OTHER DEALINGS IN THE SOFTWARE.

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