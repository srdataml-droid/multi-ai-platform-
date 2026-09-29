# Your own agent on an AWS server

Your agent (`examples/hermes_agent.py`) runs on your EC2 server and keeps running: a systemd
service where the machine uses systemd (a normal EC2 server), otherwise a small runner that
restarts it and starts it again after a reboot. It checks Novaxis every 10 seconds for customers waiting on a
reply, asks the model what to do, and sends back *proposals*. The platform's rules decide
what happens, exactly as for the built-in assistant: emergencies go to on-call first,
bookings wait for staff approval, anything risky is refused.

The model runs on Ollama Cloud (the same key and model as the platform, `gpt-oss:120b`),
so the server only relays messages: any small instance will do. No ports need opening;
the agent only makes outgoing HTTPS calls.

## Before you start

1. **Pick the business the agent answers for.** Use **Demo Restoration Services**, so the
   heating demo keeps the built-in assistant and still works while you try the agent.
2. **Create an agent key.** Sign in as `owner@demo-restoration.test` → Settings → **Your own
   agent (agent API)** → Create key. Copy it: it is shown once.
3. **Have your Ollama Cloud key ready** (ollama.com → Settings → Keys). This is a good
   moment to make a new one, since the old one was pasted in a chat.

## Install (about 5 minutes)

On your laptop, sign in to AWS the way you usually do (`aws login`), then open a shell on
the server:

```
aws ssm start-session --profile novaxis --region us-east-1 --target i-03b80a667f6695898
```

Then, on the server:

```
curl -fsSL https://raw.githubusercontent.com/srdataml-droid/multi-ai-platform-/main/deploy/aws/setup-agent.sh -o setup-agent.sh
sudo bash setup-agent.sh
```

Its first line says where it is installing (`Installing on <machine> (<system>, process 1:
…)`). If that is not your server (for example your laptop, a container or a browser shell),
stop and open the server session first: the agent stops whenever that machine does.

It asks for each setting, showing a suggestion in brackets (Enter accepts it): the Novaxis
API address, the agent key, the model service address and its key, the model, and how often
to check. Nothing is fixed in the script; any setting can also be given in the environment,
e.g. `sudo HERMES_MODEL=llama3.3 bash setup-agent.sh`. It checks both keys work, then ends
with **"Done. The agent is running"**, or with the log lines that say why not.

## Switch the business over

Dashboard (as the restoration owner) → Settings → Your own agent → **Who answers
customers** → *Our own agent, through the agent API*. From then on the built-in assistant
stays quiet for that business and your agent replies.

**Try it:** open
[novaxis-web.vercel.app/widget-demo.html?business=demo-restoration](https://novaxis-web.vercel.app/widget-demo.html?business=demo-restoration)
and write *"There's a mouldy damp patch spreading on my bedroom wall, can someone look at
it?"* A reply arrives within about 15 seconds (up to 10 s waiting for the next check, then
the model). Give the details it asks for; the booking request appears in Approvals.

Do not test with a leak or flooding: emergencies skip the agent on purpose and go straight
to the on-call contact (on the demo businesses that contact is a made-up number, so the
alert fails and the conversation waits for staff).

## Day to day (on the server)

The script's last lines print the exact commands for your machine. For reference:

| To | With systemd (EC2 server) | Without systemd |
|---|---|---|
| Watch what it does | `sudo journalctl -u novaxis-agent -f` | `sudo tail -f /var/log/novaxis-agent.log` |
| Stop it | `sudo systemctl stop novaxis-agent` | `sudo sh /opt/novaxis-agent/stop.sh` |
| Start it again | `sudo systemctl start novaxis-agent` | `sudo sh /opt/novaxis-agent/start.sh` |
| Change keys, addresses or model | `sudo bash setup-agent.sh --config` | same |
| Update to the latest agent | download `setup-agent.sh` again and run it | same |

**If the agent is stopped, that business's customers get no replies** (emergencies still
alert on-call). Switch the business back to *the built-in assistant* in Settings whenever
you stop the agent for more than a few minutes.

## Notes

- The keys are kept in `/etc/novaxis-agent.env`, readable by root only. The agent runs as
  its own user with no login and a read-only view of the system.
- The script only installs the agent if the download matches the hash written in it; the
  test suite keeps the two in step. To run your own changed agent instead:
  `sudo AGENT_FILE=/path/to/agent.py bash setup-agent.sh`.
- **If you make the GitHub repo private,** the download fails; copy the agent file to the
  server and use `AGENT_FILE` as above.
- Replying from your own server takes a little longer than the built-in assistant, because
  of the 10-second check. Webhooks remove that wait but need an HTTPS address for the
  server (docs/agent-api.md); not worth it for the pilot.
