#!/bin/sh
# Build the bash-dash sandbox image. Works from any cwd.
#   BUILD_ARCH=arm64 sandbox/build.sh        # cross-arch build
#   SANDBOX_IMAGE=foo:tag sandbox/build.sh   # custom tag
set -eu
here=$(cd "$(dirname "$0")" && pwd)
case "$(uname -m)" in
    x86_64|amd64) host_arch=amd64 ;;
    aarch64|arm64) host_arch=arm64 ;;
    *) host_arch=$(uname -m) ;;
esac
exec docker build \
    --build-arg "BUILD_PLATFORM=linux/${BUILD_ARCH:-$host_arch}" \
    -t "${SANDBOX_IMAGE:-bash-dash-sandbox:latest}" \
    "$here"
