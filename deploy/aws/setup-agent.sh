#!/usr/bin/env bash
# Runs your Novaxis agent (examples/hermes_agent.py) on a Linux server as a service that
# starts on boot and restarts itself. Amazon Linux 2023 or Ubuntu. Full steps:
# docs/agent-on-aws.md. On the server:
#
#   curl -fsSL https://raw.githubusercontent.com/srdataml-droid/multi-ai-platform-/main/deploy/aws/setup-agent.sh -o setup-agent.sh
#   sudo bash setup-agent.sh           # first time: asks for the two keys
#   sudo bash setup-agent.sh --keys    # later: change the keys or the model
#
# Running it again updates the agent. The keys are typed, never shown, and kept in
# /etc/novaxis-agent.env, which only root can read.
set -euo pipefail

REPO=https://raw.githubusercontent.com/srdataml-droid/multi-ai-platform-/main
# The agent file this script installs. apps/api/tests/test_deploy_agent.py fails when it
# changes and this hash does not, so the two cannot drift apart.
AGENT_SHA256=caca1512286dc8265299fc6a428ad6d47998aa6dae61af1422ccc6c7b7c53a87
DIR=/opt/novaxis-agent
ENV_FILE=/etc/novaxis-agent.env
UNIT=/etc/systemd/system/novaxis-agent.service

if [ "$(id -u)" -ne 0 ]; then
  echo "Run it with sudo: sudo bash setup-agent.sh" >&2
  exit 1
fi

echo "1/5 Installing Python"
if command -v dnf >/dev/null 2>&1; then
  dnf install -y -q python3 >/dev/null
elif command -v apt-get >/dev/null 2>&1; then
  apt-get update -qq && apt-get install -y -qq python3 python3-venv curl >/dev/null
else
  echo "This Linux is not Amazon Linux or Ubuntu. Install python3 (with venv), then run again." >&2
  exit 1
fi

echo "2/5 Downloading the agent"
id novaxis-agent >/dev/null 2>&1 || useradd --system --home-dir "$DIR" --shell /sbin/nologin novaxis-agent
mkdir -p "$DIR"
if ! curl -fsSL "$REPO/examples/hermes_agent.py" -o "$DIR/hermes_agent.py.new"; then
  echo "Could not download the agent. If the repo is private now, see docs/agent-on-aws.md." >&2
  exit 1
fi
if ! echo "$AGENT_SHA256  $DIR/hermes_agent.py.new" | sha256sum -c --quiet - 2>/dev/null; then
  rm -f "$DIR/hermes_agent.py.new"
  echo "The agent changed since this script was written. Download setup-agent.sh again." >&2
  exit 1
fi
mv "$DIR/hermes_agent.py.new" "$DIR/hermes_agent.py"
[ -x "$DIR/venv/bin/python" ] || python3 -m venv "$DIR/venv"
"$DIR/venv/bin/pip" install -q --disable-pip-version-check --upgrade 'httpx>=0.27,<1'

echo "3/5 Keys"
if [ ! -s "$ENV_FILE" ] || [ "${1:-}" = "--keys" ]; then
  read -rsp "Novaxis agent key (Settings > Your own agent > Create key): " AGENT_KEY
  echo
  read -rsp "Model API key (your Ollama Cloud key): " MODEL_KEY
  echo
  read -rp "Model [gpt-oss:120b]: " MODEL
  MODEL=${MODEL:-gpt-oss:120b}
  if [ -z "$AGENT_KEY" ] || [ -z "$MODEL_KEY" ]; then
    echo "Both keys are needed. Nothing was changed." >&2
    exit 1
  fi
  (
    umask 077
    cat >"$ENV_FILE" <<EOF
NOVAXIS_API=https://novaxis-api.vercel.app
NOVAXIS_AGENT_KEY=$AGENT_KEY
HERMES_BASE_URL=https://ollama.com/v1
HERMES_API_KEY=$MODEL_KEY
HERMES_MODEL=$MODEL
POLL_SECONDS=10
EOF
  )
fi
chown root:root "$ENV_FILE"
chmod 600 "$ENV_FILE"

# Check both keys before starting, so a typo shows up here and not as silence later.
set -a
# shellcheck disable=SC1090
. "$ENV_FILE"
set +a
code=$(curl -s -o /dev/null -w '%{http_code}' -H "Authorization: Bearer $NOVAXIS_AGENT_KEY" \
  "$NOVAXIS_API/agent/v1/tools")
if [ "$code" != "200" ]; then
  echo "Novaxis did not accept the agent key (HTTP $code). Run: sudo bash setup-agent.sh --keys" >&2
  exit 1
fi
code=$(curl -s -o /dev/null -w '%{http_code}' -H "Authorization: Bearer $HERMES_API_KEY" \
  -H "Content-Type: application/json" --max-time 60 "$HERMES_BASE_URL/chat/completions" \
  -d "{\"model\": \"$HERMES_MODEL\", \"messages\": [{\"role\": \"user\", \"content\": \"Say OK\"}], \"max_tokens\": 5}")
if [ "$code" != "200" ]; then
  echo "The model did not answer (HTTP $code): check its key and name. Run: sudo bash setup-agent.sh --keys" >&2
  exit 1
fi
echo "   both keys work"

echo "4/5 Service"
cat >"$UNIT" <<EOF
[Unit]
Description=Novaxis agent (examples/hermes_agent.py)
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

echo "5/5 Checking it runs"
sleep 5
if systemctl is-active --quiet novaxis-agent; then
  journalctl -u novaxis-agent -n 5 --no-pager -o cat
  echo
  echo "Done. The agent is running and restarts by itself."
  echo "Watch it:  sudo journalctl -u novaxis-agent -f"
  echo "Stop it:   sudo systemctl stop novaxis-agent"
else
  journalctl -u novaxis-agent -n 20 --no-pager -o cat
  echo "The agent did not start; the lines above say why." >&2
  exit 1
fi
