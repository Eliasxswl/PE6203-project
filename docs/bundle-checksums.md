# Stage archive checksums

Computed 2026-10-29 on the run machine (`servers/downloads/`), SHA-256, using `Get-FileHash -Algorithm SHA256`.

| Archive | Bytes | SHA-256 |
|---|---|---|
| `original_servers.zip` | 1,218,495,812 | `A66BAEE83B5D7B810E4064472FBC9030BA656A324E806AA263187E754E6935EC` |
| `iter3_servers.zip` | 1,088,423,924 | `18EF1F0C693B4D84730992211F0663817973F3FB6B436E2E77F7C082137E2391` |
| `iter5_servers.zip` | 1,088,574,402 | `67CC5ADC6959ACFA978EE67A0B53CC02F2FB064B16811D7A300A505117ACAAD1` |

Total 3,395,494,138 bytes, which matches the size published for the Hugging Face dataset `anonymous2233/evol-servers`. Extracted trees live under `servers/{original,iter3,iter5}_servers/` and are not tracked in Git.

## What these values do and do not establish

They establish that the three archives on this machine are byte-identical to a fixed set, and they let another team reproduce the extraction deterministically.

They do **not** bind archive identity to the retained formal run. That run's manifest records `tool_bundles: {"status": "missing"}` because the archives were not resolvable when it executed, so a future run should capture these hashes at run time rather than after it. The distinction matters: a hash computed later cannot prove which files the earlier run actually read.

A run-time capture would record, per stage, the archive SHA-256 plus an extracted-tree manifest (relative path and size for every launcher entry), so that extraction equivalence can be audited independently of the archive.

## Upstream comparison

The upstream repository publishes no checksums for these archives. The fork's `test_cases.json` and the four `mutation/HYBRID/evolution.json` records were separately verified byte-identical to the fork base commit `888c779`; see `benchmark_checklist.md` §0.
