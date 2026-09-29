#!/bin/sh
# Usage: sandbox-entry <dir> <slug> <base64-cmd>
# Copies one fixture dir into the /var/challenges tmpfs and execs runcmd there.
# Exit codes 64 (usage) and 65 (missing fixture) are mapped by challenges/sandbox.py.
set -eu
if [ "$#" -ne 3 ]; then
    echo "usage: sandbox-entry <dir> <slug> <base64-cmd>" >&2
    exit 64
fi
dir=$1
slug=$2
cmd=$3
src=/opt/challenges/$dir
if [ ! -d "$src" ]; then
    echo "sandbox-entry: missing fixture dir $src" >&2
    exit 65
fi
cp -a "$src" /var/challenges/
cd "/var/challenges/$dir"
exec /usr/local/bin/runcmd -cmd -slug "$slug" "$cmd"
