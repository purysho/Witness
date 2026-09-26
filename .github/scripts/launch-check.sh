#!/usr/bin/env bash
# Launch a packaged desktop app, confirm it is still running after a few
# seconds (and, optionally, that a helper process started), then close it.
# On Linux the app runs under a virtual display.
#
# usage: launch-check.sh BINARY [SECONDS] [EXPECTED_PROCESS_NAME]
#
# The expected process is matched by exact name (pgrep -x), not command line:
# this script's own arguments contain the name, so -f would always match.
set -uo pipefail

bin="$1"; wait_s="${2:-10}"; expect="${3:-}"
log="${RUNNER_TEMP:-/tmp}/launch-check.log"

if [ "$(uname)" = "Linux" ]; then
  command -v Xvfb >/dev/null || { sudo apt-get update -qq && sudo apt-get install -y -qq xvfb >/dev/null; }
  Xvfb :99 -screen 0 1600x1000x24 >/dev/null 2>&1 &
  xvfb_pid=$!
  export DISPLAY=:99
  sleep 1
fi

"$bin" >"$log" 2>&1 &
pid=$!
# With an expected helper, stop waiting as soon as it appears.
for _ in $(seq "$wait_s"); do
  sleep 1
  kill -0 "$pid" 2>/dev/null || break
  [ -n "$expect" ] && pgrep -x "$expect" >/dev/null && break
done

status=0
if ! kill -0 "$pid" 2>/dev/null; then
  echo "::error::$bin exited within ${wait_s}s"; cat "$log"; status=1
elif [ -n "$expect" ] && ! pgrep -x "$expect" >/dev/null; then
  echo "::error::$bin is running but $expect did not start"; cat "$log"
  ps -eo pid,ppid,comm,args | grep -v " ps -eo" | tail -n 40; status=1
else
  echo "$bin is running${expect:+ and $expect started}"
fi

pkill -P "$pid" 2>/dev/null; kill "$pid" 2>/dev/null
[ -n "$expect" ] && pkill -x "$expect" 2>/dev/null
[ -n "${xvfb_pid:-}" ] && kill "$xvfb_pid" 2>/dev/null
exit $status
