# Contributing

Thanks for considering a contribution — PRs and issues are welcome.

## Ways to contribute
- **Bug reports:** open an issue with your Wazuh version, n8n version, and (if
  possible) a sanitized copy of the alert JSON that triggered the problem.
- **New enrichment sources:** additional threat intel (e.g. Shodan, GreyNoise,
  OTX) are great additions — follow the existing pattern of a single Code node
  per source that fails gracefully (`checked: false`) rather than blocking
  the pipeline.
- **Different AI backends:** if you swap Ollama for OpenAI/Claude/Gemini and
  it works well, a PR with the equivalent HTTP Request node config (and a
  note in the README) is very welcome.
- **Report design:** the IR report HTML lives entirely in the *Generate IR
  Report* Code node — improvements there are easy to review as a diff of
  that one node's `jsCode`.

## Before opening a PR
1. Re-export the workflow from n8n (**Download** from the workflow menu) so
   `workflow/wazuh-ai-soc-agent.json` reflects your actual changes, not a
   hand-edited file.
2. Run it end-to-end against at least one real (or realistic sample) Wazuh
   alert and confirm the report/notifications still generate correctly.
3. Don't commit real API keys, webhook URLs, or credentials — check your
   diff against `.env.example` before pushing.
4. Update `docs/SETUP_GUIDE.md` if you add a new environment variable or
   change the required Wazuh-side configuration.

## Code style
- Keep Code nodes readable — this project favors explicit, commented
  JavaScript over cleverness, since the whole point is that a SOC engineer
  who isn't a JS developer can still read and adapt it.
- Sticky notes are part of the UX here, not decoration — if you add a new
  functional cluster of nodes, add a sticky note describing it too.

## Security-sensitive changes
Anything touching the **Auto-Block Safeguard Check** node gets extra
scrutiny — please explain in the PR description exactly what new condition
you're adding and why it can't produce a false-positive block.
