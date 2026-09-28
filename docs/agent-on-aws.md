# Your own agent on an AWS server

Your agent (`examples/hermes_agent.py`) runs on your EC2 server as a service that starts on
boot and restarts itself. It checks Novaxis every 10 seconds for customers waiting on a
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

It asks for the agent key, the Ollama key and the model (press Enter for `gpt-oss:120b`).
It checks both keys work before starting, then ends with **"Done. The agent is running"**.

## Switch the business over

Dashboard (as the restoration owner) → Settings → Your own agent → **Who answers
customers** → *Our own agent, through the agent API*. From then on the built-in assistant
stays quiet for that business and your agent replies.

**Try it:** open
[novaxis-web.vercel.app/widget-demo.html?business=demo-restoration](https://novaxis-web.vercel.app/widget-demo.html?business=demo-restoration)
and write *"Water is coming through my kitchen ceiling from the flat upstairs."* A reply
arrives within about 15 seconds (up to 10 s waiting for the next check, then the model).
Give the details it asks for; the booking request appears in Approvals.

## Day to day (on the server)

| To | Run |
|---|---|
| Watch what it does | `sudo journalctl -u novaxis-agent -f` |
| Stop it | `sudo systemctl stop novaxis-agent` |
| Start it again | `sudo systemctl start novaxis-agent` |
| Change the keys or model | `sudo bash setup-agent.sh --keys` |
| Update to the latest agent | download `setup-agent.sh` again and run it |

**If the agent is stopped, that business's customers get no replies** (emergencies still
alert on-call). Switch the business back to *the built-in assistant* in Settings whenever
you stop the agent for more than a few minutes.

## Notes

- The keys are kept in `/etc/novaxis-agent.env`, readable by root only. The agent runs as
  its own user with no login and a read-only view of the system.
- The script only installs the agent if the download matches the hash written in it; the
  test suite keeps the two in step.
- **If you make the GitHub repo private,** the download needs a token. Run the install
  before making it private, or ask for a version of the script that carries the agent
  inside it.
- Replying from your own server takes a little longer than the built-in assistant, because
  of the 10-second check. Webhooks remove that wait but need an HTTPS address for the
  server (docs/agent-api.md); not worth it for the pilot.
