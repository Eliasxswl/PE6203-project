# Role 1: Selective Patch

custom.experiment.selective_patch is a deterministic, local strategy plugin.
It compares the prior and target semantic tool catalogs and updates only their
detected differences. It makes no model or network requests.

## Algorithm

1. Tool identities are server::tool.
2. A tool present only in the target catalog is added; one present only in the
   prior catalog is removed.
3. For a shared tool, description is replaced only when it differs.
4. inputSchema dictionaries are patched recursively. Added, removed, and
   changed schema values are recorded as JSON Pointer-like paths. Lists and
   scalar values are replaced atomically.
5. Shared tools with no semantic difference are not changed.

The audit entry for every affected tool includes a TOOL, PARAM, DESC, or MIXED
classification, the applied operations, and an explanation. The strategy
reports zero model calls and zero model-token cost.

## Configuration example

This is an example only. Do not edit the formal experiment configuration until
Role 3 freezes the task set and its candidate hash.

~~~json
{
  "strategies": ["no_update", "full_rewrite", "selective_patch"],
  "strategy_plugins": ["custom.experiment.selective_patch"]
}
~~~

The pipeline imports the module before validation. The plugin registers itself
as selective_patch, so Role 2 only needs to add the module name and strategy
name to a newly frozen experiment configuration.

## Offline test

~~~text
python -m unittest tests.test_selective_patch -v
~~~

This test requires no API key, downloaded server bundle, MCP process, or
network access.
