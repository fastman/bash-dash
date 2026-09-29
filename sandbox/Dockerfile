# syntax=docker/dockerfile:1
# vi: ft=dockerfile
# Derived from upstream cmdchallenge Dockerfile-cmd (see README.md).
ARG BUILD_PLATFORM=linux/amd64

FROM --platform=${BUILD_PLATFORM} golang:1.24 AS builder
WORKDIR /app
COPY go.mod go.sum ./
COPY cmd/ cmd/
COPY internal/ internal/
# Static binary: -cmd mode never opens the sqlite store, so cgo is not needed.
RUN --mount=type=cache,target=/root/.cache/go-build \
    --mount=type=cache,target=/go/pkg/mod \
    CGO_ENABLED=0 go build -ldflags "-w" -o /out/runcmd ./cmd/runcmd

FROM --platform=${BUILD_PLATFORM} ubuntu:22.04
RUN apt-get update && \
      apt-get install -y --no-install-recommends jq bc rename bsdmainutils man file && \
      rm -rf /var/lib/apt/lists/* && \
      rm -f /etc/bash.bashrc && rm -rf /etc/bash_completion.d && \
      rm -f /root/.bashrc && \
      groupadd -g 1000 player && \
      useradd -u 1000 -g 1000 -M -d /nonexistent -s /usr/sbin/nologin player && \
      mkdir -p /var/challenges
COPY --from=builder /out/runcmd /usr/local/bin/runcmd
COPY --chmod=0755 sandbox-entry.sh /usr/local/bin/sandbox-entry
# Fixtures live at /opt/challenges; the entrypoint copies one dir into the
# /var/challenges tmpfs at run time.
COPY --chown=1000:1000 var/challenges/ /opt/challenges/
USER player
ENTRYPOINT ["/usr/local/bin/sandbox-entry"]
