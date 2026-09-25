# AI SOC Agent — Setup Guide
### Wazuh → n8n → Ollama → Auto-Response & IR Reporting

This workflow turns raw Wazuh alerts into the same triage/escalation decisions an
L1/L2 SOC analyst would make: validate → dedupe → filter by severity → enrich with
threat intel → AI analysis (verdict, MITRE mapping, confidence) → safeguarded
auto-block → incident report → Slack + email.

---

## 1. Import the workflow
1. Open n8n → **Workflows → Import from File** → select `wazuh-ai-soc-agent.json`.
2. Open each **Slack** and **Gmail** node and select/create your own credential
   (OAuth). Credentials are never embedded in an exported workflow, so this step
   is required regardless of who built the file.
3. Note the webhook's production URL from the **Wazuh Alert Webhook** node
   (`.../webhook/wazuh-alert`) — you'll need it in step 2.

## 2. Point Wazuh at the webhook
Custom Wazuh integrations (any target that isn't Slack/PagerDuty/VirusTotal/
Shuffle/Maltiverse) need a script — Wazuh's `wazuh-integratord` doesn't POST
to an arbitrary URL on its own for custom names, it hands off to a script
matching the integration `name`. Two files are included for this:
`custom-n8n-soc` (shell launcher) and `custom-n8n-soc.py` (does the actual POST).

1. Copy both files to the manager:
   ```bash
   cp custom-n8n-soc custom-n8n-soc.py /var/ossec/integrations/
   chmod 750 /var/ossec/integrations/custom-n8n-soc /var/ossec/integrations/custom-n8n-soc.py
   chown root:wazuh /var/ossec/integrations/custom-n8n-soc /var/ossec/integrations/custom-n8n-soc.py
   ```
2. Confirm `requests` is available to Wazuh's bundled Python (most installs
   already have it via other integrations; if not):
   ```bash
   /var/ossec/framework/python/bin/python3 -m pip install requests
   ```
3. Add the integration block to `/var/ossec/etc/ossec.conf` (note the name
   **must** start with `custom-` and match the script filename exactly):
   ```xml
   <integration>
     <name>custom-n8n-soc</name>
     <hook_url>https://YOUR_N8N_HOST/webhook/wazuh-alert</hook_url>
     <api_key>a-shared-secret-you-choose</api_key>  <!-- optional but recommended -->
     <level>7</level>
     <alert_format>json</alert_format>
   </integration>
   ```
   The `api_key` (if set) is sent as an `X-Webhook-Secret` header on every
   POST — add an IF node right after the Webhook trigger in n8n to check that
   header matches, so random internet traffic can't feed fake alerts into
   your auto-block logic.
4. Restart the manager and watch the log while you trigger a test alert:
   ```bash
   systemctl restart wazuh-manager
   tail -f /var/ossec/logs/integrations.log
   ```
   You should see `custom-n8n-soc: POST ... -> HTTP 200` (or your response
   code) for each qualifying alert. If nothing appears, check
   `/var/ossec/logs/ossec.log` for integratord startup errors first.

> Alternative: if you'd rather have n8n *pull* alerts instead of Wazuh pushing
> them, swap the Webhook trigger for a **Schedule Trigger + HTTP Request** node
> against the Wazuh Indexer's `_search` API — everything downstream is unchanged.

## 3. Set environment variables (Configuration Center)
The **Configuration Center** node reads these via `$env`. Set them in n8n
(Settings → Environment Variables, or your `.env` if self-hosted):

| Variable | Purpose | Default |
|---|---|---|
| `SOC_SEVERITY_THRESHOLD` | Min `rule.level` to process at all | `7` |
| `SOC_CRITICAL_THRESHOLD` | Min `rule.level` eligible for auto-block | `12` |
| `SOC_AUTO_BLOCK_ENABLED` | Master kill switch for auto-block | `true` |
| `SOC_DEDUPE_WINDOW_MIN` | Minutes to suppress repeat alerts | `15` |
| `SOC_INTERNAL_CIDRS` | Comma-separated CIDRs that must never be blocked | RFC1918 ranges |
| `SOC_ALLOWLIST_IPS` | Comma-separated IPs excluded from auto-block | empty |
| `SOC_CRITICAL_ASSETS` | Agent names/IDs that require human approval before any block | empty |
| `OLLAMA_URL` | Ollama generate endpoint | `http://localhost:11434/api/generate` |
| `OLLAMA_MODEL` | Model to use for triage | `llama3.1:8b` |
| `ABUSEIPDB_API_KEY` | Free tier key from abuseipdb.com — IP reputation | — |
| `VIRUSTOTAL_API_KEY` | Free tier key from virustotal.com — malware/hash analysis | — |
| `WAZUH_API_URL` | Used for the active-response block call | `https://localhost:55000` |
| `SOC_L2_ESCALATION_EMAIL` / `SOC_L2_REVIEW_EMAIL` | Where critical / suspicious reports go | — |
| `SOC_ORG_NAME` | Cosmetic, shown on the report footer | — |

## 4. Wazuh active response (for the auto-block branch)
Add a matching active response definition on the Wazuh manager so the
`firewall-drop0` command the workflow calls actually exists:

```xml
<command>
  <name>firewall-drop0</name>
  <executable>firewall-drop</executable>
  <timeout_allowed>yes</timeout_allowed>
</command>
<active-response>
  <command>firewall-drop0</command>
  <location>local</location>
</active-response>
```
You'll also need a Wazuh API user with active-response permissions, passed via
an `httpHeaderAuth` credential on the **Wazuh Active Response - Block IP** node.

## 5. Pull the Ollama model
```bash
ollama pull llama3.1:8b
ollama serve
```
Any local model works — swap `OLLAMA_MODEL`. For stricter JSON reliability,
models that support function-calling / JSON mode well (Llama 3.1, Qwen2.5,
Mistral) behave best. Swapping to OpenAI or Claude just means replacing the
**Ollama AI Analysis** HTTP node with the corresponding node/credential — the
prompt and downstream parsing stay identical.

## 6. Test it
Send a sample alert straight to the webhook to dry-run the pipeline without
touching Wazuh:

```bash
curl -X POST https://YOUR_N8N_HOST/webhook-test/wazuh-alert \
  -H "Content-Type: application/json" \
  -d '{
    "id": "1700000000.123456",
    "timestamp": "2026-09-18T12:00:00.000+0000",
    "rule": {"id": "5710", "level": 10, "description": "Multiple authentication failures", "groups": ["authentication_failures"]},
    "agent": {"id": "001", "name": "web-server-01", "ip": "10.0.1.15"},
    "data": {"srcip": "185.220.101.45", "srcuser": "root"},
    "full_log": "Sep 18 12:00:00 web-server-01 sshd[1234]: Failed password for root from 185.220.101.45 port 51234 ssh2"
  }'
```

## What each pipeline stage does (mapped to the sections in the reference diagram)
- **Configuration Center** — single node holding every tunable (thresholds, allowlists, API endpoints).
- **Input Validation** — rejects malformed/incomplete Wazuh payloads before they touch anything else.
- **Deduplication** — rolling-window suppression so the same brute-force alert doesn't re-fire the AI/notify path every second.
- **IP Reputation & Geo Footprint** — AbuseIPDB (abuse score, Tor/usage type) + ip-api.com (city/country, ASN/ISP, proxy/hosting flags). No key needed for geolocation (ip-api.com free tier, ~45 req/min).
- **Malware Analysis** — VirusTotal file-hash lookup: detection ratio, file type, threat classification, known aliases, signature status.
- **Vulnerability / CVSS** — reads Wazuh's own vulnerability-detector fields (CVE, CVSS score/vector, affected package + installed version, fix condition) directly off the alert, and optionally cross-references NVD for a public description/reference link. Only runs when the alert actually carries `data.vulnerability`.
- **AI Analysis Pipeline** — local Ollama call, forced into strict JSON, producing verdict/confidence/MITRE mapping/kill-chain stage/business impact/recommended actions — factoring in all of the enrichment above.
- **Auto-Block with Safeguards** — never fires on internal IPs, allowlisted IPs, critical assets, low-confidence verdicts, or sub-critical severity, and is globally kill-switchable.
- **Notification & Response** — Slack gets one minimal line per alert (verdict, confidence, rule, asset, CVSS if present); the full Red/Blue/White HTML report goes by email, tiered by verdict (critical auto-block channel vs. L2 review channel; benign is auto-closed with no notification, like a real L1 queue).
- **Error Handling** — a dedicated Error Trigger catches any node failure workflow-wide and pages a Slack channel with the failing node + message.

## Report design
The email report (see `sample_email_report_preview.html` / the published preview link) follows a standard CERT/SOC layout: white body, navy-blue for structure and headers, and **red reserved strictly for risk signals** — a malicious verdict, a CVSS ≥ 7, a positive malware detection, Tor/proxy IPs, or a critical asset. Blue is used for informational/neutral data so red always means "look here first." Sections only render when relevant — the Vulnerability and Malware Analysis blocks are omitted entirely when an alert has no CVE or file hash.

## Limitations to know before relying on this
- Auto-block calls a Wazuh active-response command; if you use a different
  firewall/EDR, swap that one HTTP Request node's URL/body.
- The AI verdict is only as good as the local model — treat "malicious" +
  auto-block as provisional and keep the safeguard thresholds conservative
  until you've watched it run for a while.
- This is a template, not a certified SOAR product — pressure-test the
  dedupe/severity thresholds against your actual alert volume before turning
  `SOC_AUTO_BLOCK_ENABLED` on in production.
