#!/var/ossec/framework/python/bin/python3
"""
custom-n8n-soc.py
Forwards Wazuh alerts to the n8n AI SOC Agent webhook.

Called by Wazuh's integratord as:
    custom-n8n-soc <alert_file> <api_key> <hook_url> [options_json]

- <alert_file>  path to a JSON file containing the single alert that fired
- <api_key>     value of <api_key> in ossec.conf (optional) - used here as a
                 shared secret sent in the "X-Webhook-Secret" header so your
                 n8n webhook can reject unauthenticated requests
- <hook_url>    value of <hook_url> in ossec.conf - your n8n webhook URL
- [options_json] present only if <options>{"debug":true}</options> was set

stdout is captured by Wazuh into /var/ossec/logs/integrations.log.
"""

import json
import sys
import time

try:
    import requests
except ImportError:
    print("custom-n8n-soc: python module 'requests' not found. "
          "Install it into Wazuh's bundled interpreter with: "
          "/var/ossec/framework/python/bin/python3 -m pip install requests")
    sys.exit(1)

RETRIES = 2
TIMEOUT_SECONDS = 10


def main(args):
    debug_enabled = False

    try:
        alert_file_location = args[1]
        api_key = args[2] if len(args) > 2 else ""
        hook_url = args[3] if len(args) > 3 else ""
    except IndexError:
        print("custom-n8n-soc: missing required arguments (alert_file, api_key, hook_url)")
        sys.exit(1)

    if not hook_url:
        print("custom-n8n-soc: no hook_url configured in ossec.conf <integration> block")
        sys.exit(1)

    # optional <options>{"debug": true}</options>
    if len(args) > 4:
        try:
            options = json.loads(args[4])
            debug_enabled = bool(options.get("debug", False))
        except (ValueError, IndexError):
            pass

    try:
        with open(alert_file_location, "r") as f:
            alert_json = json.load(f)
    except Exception as e:
        print(f"custom-n8n-soc: failed to read/parse alert file: {e}")
        sys.exit(1)

    send_to_n8n(alert_json, hook_url, api_key, debug_enabled)


def send_to_n8n(alert, hook_url, api_key, debug_enabled):
    headers = {"Content-Type": "application/json"}
    if api_key:
        # Used as a shared secret, not an OAuth token - configure an n8n
        # "IF" node (or Header Auth on the webhook) to check for this value.
        headers["X-Webhook-Secret"] = api_key

    payload = json.dumps(alert)

    last_error = None
    for attempt in range(1, RETRIES + 2):
        try:
            resp = requests.post(hook_url, data=payload, headers=headers, timeout=TIMEOUT_SECONDS)
            if debug_enabled:
                print(f"custom-n8n-soc: POST {hook_url} -> HTTP {resp.status_code} (attempt {attempt})")
            if resp.status_code < 300:
                return
            last_error = f"HTTP {resp.status_code}: {resp.text[:200]}"
        except requests.exceptions.RequestException as e:
            last_error = str(e)

        if attempt <= RETRIES:
            time.sleep(1.5 * attempt)

    print(f"custom-n8n-soc: failed to deliver alert after {RETRIES + 1} attempts - {last_error}")


if __name__ == "__main__":
    main(sys.argv)
