#!/usr/bin/env bash
# Runs your Novaxis agent (examples/hermes_agent.py) on a Linux machine and keeps it
# running: a systemd service where systemd runs the machine (a normal EC2 server), else a
# small background runner that restarts it. Full steps: docs/agent-on-aws.md.
#
#   curl -fsSL https://raw.githubusercontent.com/srdataml-droid/multi-ai-platform-/main/deploy/aws/setup-agent.sh -o setup-agent.sh
#   sudo bash setup-agent.sh            # first time: asks for every setting
#   sudo bash setup-agent.sh --config   # later: change keys, addresses or model
#
# Nothing is fixed in here: every setting is asked for (Enter keeps the value shown) or
# can be given in the environment, e.g. sudo NOVAXIS_API=https://api.example.com bash ...
# Settings live in /etc/novaxis-agent.env, readable by root only; keys are never shown.
set -euo pipefail

DIR=${AGENT_DIR:-/opt/novaxis-agent}
ENV_FILE=${AGENT_ENV_FILE:-/etc/novaxis-agent.env}
LOG=${AGENT_LOG:-/var/log/novaxis-agent.log}
UNIT=/etc/systemd/system/novaxis-agent.service
# Where the agent comes from. By default: this repo, at the commit this script was written
# for, checked against its hash (GitHub serves `main` from a cache for up to five minutes,
# and the hash stops a changed or tampered file). apps/api/tests/test_deploy_agent.py
# fails when the agent changes and these do not. Your own copy: AGENT_FILE=/path/agent.py.
AGENT_COMMIT=${AGENT_COMMIT:-a32282ad5ff34b794e4d254e7ac99b535f09a7f3}
AGENT_SHA256=${AGENT_SHA256:-caca1512286dc8265299fc6a428ad6d47998aa6dae61af1422ccc6c7b7c53a87}
AGENT_URL=${AGENT_URL:-https://raw.githubusercontent.com/srdataml-droid/multi-ai-platform-/$AGENT_COMMIT/examples/hermes_agent.py}
AGENT_FILE=${AGENT_FILE:-}

if [ "$(id -u)" -ne 0 ]; then
  echo "Run it with sudo: sudo bash setup-agent.sh" >&2
  exit 1
fi

# Where are we? A laptop, a container or a browser shell stops the agent when it stops.
os=$( (. /etc/os-release 2>/dev/null && echo "$PRETTY_NAME") || uname -s)
init=$(ps -p 1 -o comm= 2>/dev/null || echo unknown)
echo "Installing on $(hostname) ($os, process 1: $init)"
if [ -d /run/systemd/system ]; then
  MODE=systemd
else
  MODE=runner
  for tool in runuser setsid nohup; do
    command -v "$tool" >/dev/null 2>&1 || { echo "Needs $tool (util-linux); install it and run again." >&2; exit 1; }
  done
  echo "   No systemd here, so the agent runs under a small restarting runner instead."
  echo "   If this is not your always-on server (for example a laptop, a container or a"
  echo "   browser shell), the agent stops when this machine or session does."
fi

echo "1/5 Python"
if command -v python3 >/dev/null 2>&1 && python3 -c 'import venv, ensurepip' >/dev/null 2>&1; then
  :
elif command -v dnf >/dev/null 2>&1; then
  dnf install -y -q python3 >/dev/null
elif command -v apt-get >/dev/null 2>&1; then
  apt-get update -qq && apt-get install -y -qq python3 python3-venv curl >/dev/null
elif command -v apk >/dev/null 2>&1; then
  apk add -q python3 py3-pip curl >/dev/null
else
  echo "Install python3 (with venv) with this system's package manager, then run again." >&2
  exit 1
fi

echo "2/5 The agent"
id novaxis-agent >/dev/null 2>&1 || useradd --system --home-dir "$DIR" --shell /sbin/nologin novaxis-agent 2>/dev/null \
  || adduser -S -h "$DIR" -s /sbin/nologin novaxis-agent
mkdir -p "$DIR"
if [ -n "$AGENT_FILE" ]; then
  cp "$AGENT_FILE" "$DIR/hermes_agent.py.new"
  echo "   using your file $AGENT_FILE (not hash-checked)"
else
  if ! curl -fsSL "$AGENT_URL" -o "$DIR/hermes_agent.py.new"; then
    echo "Could not download $AGENT_URL. A private repo needs AGENT_FILE (docs/agent-on-aws.md)." >&2
    exit 1
  fi
  if ! echo "$AGENT_SHA256  $DIR/hermes_agent.py.new" | sha256sum -c --quiet - >/dev/null 2>&1; then
    rm -f "$DIR/hermes_agent.py.new"
    echo "The download does not match AGENT_SHA256. Download setup-agent.sh again." >&2
    exit 1
  fi
fi
mv "$DIR/hermes_agent.py.new" "$DIR/hermes_agent.py"
[ -x "$DIR/venv/bin/python" ] || python3 -m venv "$DIR/venv"
"$DIR/venv/bin/pip" install -q --disable-pip-version-check --upgrade 'httpx>=0.27,<1'

echo "3/5 Settings"
# Current values: the environment first, then the settings file, then a suggestion.
current() { # name, suggestion
  local v="${!1:-}"
  if [ -z "$v" ] && [ -s "$ENV_FILE" ]; then v=$(sed -n "s/^$1=//p" "$ENV_FILE" | tail -1); fi
  echo "${v:-$2}"
}
# Asked on the first run and with --config; otherwise the saved value is kept. A value
# given in the environment is never asked for.
RECONFIGURE=0
if [ ! -s "$ENV_FILE" ] || [ "${1:-}" = "--config" ] || [ "${1:-}" = "--keys" ]; then
  RECONFIGURE=1
fi
ask() { # name, question, suggestion
  local now ans
  now=$(current "$1" "$3")
  if [ -z "${!1:-}" ] && [ "$RECONFIGURE" = 1 ]; then
    read -rp "$2 [$now]: " ans
    now=${ans:-$now}
  fi
  printf -v "$1" '%s' "$now"
}
ask_secret() { # name, question
  local now ans
  now=$(current "$1" "")
  if [ -z "${!1:-}" ] && { [ "$RECONFIGURE" = 1 ] || [ -z "$now" ]; }; then
    read -rsp "$2${now:+ (Enter keeps the saved one)}: " ans
    echo
    now=${ans:-$now}
  fi
  printf -v "$1" '%s' "$now"
}

ask NOVAXIS_API "Novaxis API address" "https://novaxis-api.vercel.app"
ask_secret NOVAXIS_AGENT_KEY "Novaxis agent key (Settings > Your own agent > Create key)"
ask HERMES_BASE_URL "Model service address (OpenAI-compatible)" "https://ollama.com/v1"
ask_secret HERMES_API_KEY "Model service key"
ask HERMES_MODEL "Model" "gpt-oss:120b"
ask POLL_SECONDS "Seconds between checks for new messages" "10"
if [ -z "$NOVAXIS_AGENT_KEY" ] || [ -z "$HERMES_API_KEY" ]; then
  echo "Both keys are needed. Nothing was changed." >&2
  exit 1
fi
(
  umask 077
  printf '%s\n' "NOVAXIS_API=$NOVAXIS_API" "NOVAXIS_AGENT_KEY=$NOVAXIS_AGENT_KEY" \
    "HERMES_BASE_URL=$HERMES_BASE_URL" "HERMES_API_KEY=$HERMES_API_KEY" \
    "HERMES_MODEL=$HERMES_MODEL" "POLL_SECONDS=$POLL_SECONDS" >"$ENV_FILE.new"
)
mv "$ENV_FILE.new" "$ENV_FILE"
chown root:root "$ENV_FILE"
chmod 600 "$ENV_FILE"

# Check both before starting, so a typo shows up here and not as silence later.
code=$(curl -s -o /dev/null -w '%{http_code}' --max-time 30 \
  -H "Authorization: Bearer $NOVAXIS_AGENT_KEY" "$NOVAXIS_API/agent/v1/tools" || true)
if [ "$code" != "200" ]; then
  echo "Novaxis did not accept the agent key at $NOVAXIS_API (HTTP $code)." >&2
  echo "Run: sudo bash setup-agent.sh --config" >&2
  exit 1
fi
code=$(curl -s -o /dev/null -w '%{http_code}' --max-time 60 \
  -H "Authorization: Bearer $HERMES_API_KEY" -H "Content-Type: application/json" \
  "$HERMES_BASE_URL/chat/completions" \
  -d "{\"model\": \"$HERMES_MODEL\", \"messages\": [{\"role\": \"user\", \"content\": \"Say OK\"}], \"max_tokens\": 5}" || true)
if [ "$code" != "200" ]; then
  echo "The model $HERMES_MODEL at $HERMES_BASE_URL did not answer (HTTP $code)." >&2
  echo "Run: sudo bash setup-agent.sh --config" >&2
  exit 1
fi
echo "   Novaxis and the model both answered"

echo "4/5 Keeping it running ($MODE)"
if [ "$MODE" = systemd ]; then
  cat >"$UNIT" <<EOF
[Unit]
Description=Novaxis agent
After=network-online.target
Wants=network-online.target

[Service]
User=novaxis-agent
EnvironmentFile=$ENV_FILE
ExecStart=$DIR/venv/bin/python -u $DIR/hermes_agent.py
Restart=always
RestartSec=10
NoNewPrivileges=true
ProtectSystem=strict
ProtectHome=true
PrivateTmp=true

[Install]
WantedBy=multi-user.target
EOF
  systemctl daemon-reload
  systemctl enable novaxis-agent >/dev/null 2>&1
  systemctl restart novaxis-agent
else
  # Like systemd: the agent starts from a clean environment holding only its settings,
  # read as root and handed over in the environment (never on a command line others
  # could see), and runs as its own user.
  cat >"$DIR/run.sh" <<EOF
#!/bin/sh
while true; do
  env -i PATH=/usr/sbin:/usr/bin:/sbin:/bin sh -c 'set -a; . "\$0"; set +a; exec runuser -u novaxis-agent -- "\$1" -u "\$2"' \\
    "$ENV_FILE" "$DIR/venv/bin/python" "$DIR/hermes_agent.py"
  echo "agent stopped (exit \$?); starting again in 10 s"
  sleep 10
done
EOF
  cat >"$DIR/start.sh" <<EOF
#!/bin/sh
[ -f "$DIR/runner.pid" ] && kill -- -"\$(cat "$DIR/runner.pid")" 2>/dev/null
nohup setsid sh "$DIR/run.sh" >>"$LOG" 2>&1 </dev/null &
echo \$! >"$DIR/runner.pid"
EOF
  cat >"$DIR/stop.sh" <<EOF
#!/bin/sh
[ -f "$DIR/runner.pid" ] && kill -- -"\$(cat "$DIR/runner.pid")" 2>/dev/null
rm -f "$DIR/runner.pid"
EOF
  chmod 700 "$DIR/run.sh" "$DIR/start.sh" "$DIR/stop.sh"
  touch "$LOG" && chmod 640 "$LOG"
  LOG_FROM=$(wc -c <"$LOG")
  sh "$DIR/start.sh"
  if command -v crontab >/dev/null 2>&1; then
    (crontab -l 2>/dev/null | grep -v "$DIR/start.sh"; echo "@reboot sh $DIR/start.sh") | crontab -
  fi
fi

echo "5/5 Checking it runs"
sleep 8
if [ "$MODE" = systemd ]; then
  running=$(systemctl is-active novaxis-agent || true)
  logs() { journalctl -u novaxis-agent -n "$1" --no-pager -o cat; }
  watch="sudo journalctl -u novaxis-agent -f"
  stop="sudo systemctl stop novaxis-agent"
else
  # Alive, and not restarting after a crash since it was started.
  running=stopped
  if kill -0 "$(cat "$DIR/runner.pid")" 2>/dev/null \
    && ! tail -c +"$((LOG_FROM + 1))" "$LOG" | grep -q "agent stopped"; then
    running=active
  fi
  logs() { tail -c +"$((LOG_FROM + 1))" "$LOG" | tail -n "$1"; }
  watch="sudo tail -f $LOG"
  stop="sudo sh $DIR/stop.sh"
fi
if [ "$running" = active ]; then
  logs 5
  echo
  echo "Done. The agent is running and restarts by itself."
  echo "Watch it:  $watch"
  echo "Stop it:   $stop"
else
  logs 20
  echo "The agent did not start; the lines above say why." >&2
  exit 1
fi
