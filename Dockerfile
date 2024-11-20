FROM registry.access.redhat.com/ubi9/ubi-minimal:latest as base

RUN microdnf update -y && \
    microdnf install -y \
        git python-pip && \
    pip install --upgrade --no-cache-dir pip wheel && \
    microdnf clean all

WORKDIR /build

RUN pip install --no-cache tox
COPY README.md .
COPY pyproject.toml .
COPY tox.ini .
COPY caikit_nlp caikit_nlp
# .git is required for setuptools-scm get the version
RUN --mount=source=.git,target=.git,type=bind \
    --mount=type=cache,target=/root/.cache/pip \
     tox -e build

RUN python -m venv --upgrade-deps /opt/caikit/

ENV VIRTUAL_ENV=/opt/caikit
ENV PATH="$VIRTUAL_ENV/bin:$PATH"

RUN cp /build/dist/caikit_nlp*.whl /tmp/
RUN --mount=type=cache,target=/root/.cache/pip \
    pip install /tmp/caikit_nlp*.whl && \
    rm /tmp/caikit_nlp*.whl

COPY LICENSE /opt/caikit/
COPY README.md /opt/caikit/

RUN groupadd --system caikit --gid 1001 && \
    adduser --system --uid 1001 --gid 0 --groups caikit \
    --home-dir /caikit --shell /sbin/nologin \
    --comment "Caikit User" caikit

USER caikit

ENV RUNTIME_LIBRARY=caikit_nlp
# Optional: use `CONFIG_FILES` and the /caikit/ volume to explicitly provide a configuration file and models
# ENV CONFIG_FILES=/caikit/caikit.yml
VOLUME ["/caikit/"]
WORKDIR /caikit

CMD ["python"]
