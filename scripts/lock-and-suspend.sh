#!/usr/bin/env bash
set -euo pipefail

script_dir="$(cd -- "$(dirname -- "$0")" && pwd)"
runtime_dir="${XDG_RUNTIME_DIR:-/tmp}"
work_dir="$(mktemp -d "$runtime_dir/swaylock-suspend.XXXXXX")"
ready_pipe="$work_dir/ready"

cleanup() {
    rm -rf "$work_dir"
}
trap cleanup EXIT

mkfifo "$ready_pipe"

"$script_dir/lock-screen.sh" --ready-fd 3 3>"$ready_pipe" &
lock_pid=$!

if ! IFS= read -r _ < "$ready_pipe"; then
    wait "$lock_pid"
    exit 1
fi

systemctl suspend
wait "$lock_pid"
