# Method: how the three strategies differ

This page explains the design in one place. Implementation detail for the selective patch itself is in [selective_patch.md](selective_patch.md); this page covers what is common, what is different, and why the difference is measurable.

## Knowledge has two layers

| Layer | What it holds | How it is produced |
|---|---|---|
| Catalog knowledge | `server::tool` → name, description, `inputSchema` | Deterministic, read from the stage's `tools/list` |
| Experience layer | Operational notes on how to use tools in practice | Written by a paid updater model, seeded from `config/practice/shrimp-k0.json` |

Transport routing is deliberately excluded from both layers, so a strategy cannot "adapt" by quietly re-pointing a server.

## Strategy matrix

| Strategy | Catalog knowledge | Experience layer |
|---|---|---|
| No Update | Frozen at Early | Frozen at Early |
| Full Rewrite | Rebuilt from the current catalog (`semantic(new_tools)`) | Updater rewrites every entry |
| Selective Patch | Only differing fields patched | Updater rewrites only entries tied to changed tools |

## Why Full Rewrite and Selective Patch hold the same catalog knowledge

The catalog layer is a pure function of the current catalog: `semantic(new_tools)` for Full Rewrite, and a field-by-field patch for Selective Patch. When the starting state is a complete catalog, both end at the same values. The implemented patch keeps unchanged fields untouched, but "untouched" and "rewritten to an identical value" produce the same record.

Verified on the formal run: `knowledge_sha256` is equal in **153 of 153** Full Rewrite / Selective Patch pairs. Any score difference between the two strategies therefore cannot come from catalog content. It can only come from the experience layer, and there `experience_state_sha256` differs on **102 of 153** pairs.

This is the single most important design fact to state when presenting the comparison. It also explains the update-cost gap: the catalog rebuild is free, while the experience rewrite is the part that calls a model.

## Detection

Both strategies consume the same catalog diff; the patch applies it and the updater uses it to decide which experience entries to rewrite.

```text
for tool_id in union(previous_catalog, current_catalog):
    if tool_id not in previous_catalog:  -> added
    elif tool_id not in current_catalog: -> removed
    elif description differs:            -> description change
    elif inputSchema differs anywhere:   -> parameter change (JSON-Pointer path per field)
    else:                                -> unchanged, do not touch

change_type per affected tool = TOOL | PARAM | DESC | MIXED
```

The comparison is exact equality on nested schema values. Dictionaries are traversed recursively so unrelated sibling fields survive; lists and scalars are replaced atomically. There is no embedding distance and no threshold, so the detector has no recall parameter to tune.

## Controls used to make the comparison interpretable

1. **Matched identities.** Scores are compared only on identical `task/stage/repeat` cells, never between independently aggregated groups.
2. **Cohort split.** The 4 changed tasks and the 13 retention controls are reported separately, because the controls sit near the top of the scale and dilute any pooled effect.
3. **Equal-length control.** The Task 9 case adds an equal-length JSON key-order variant to separate "the record got longer" from "the record got rewritten". It scored 0/10 against 10/10 for the restored set, so length alone does not explain the recovery.

## Known limitation of this design

The catalog layer being equal by construction means the study compares **two experience-layer policies**, not "a smart patch versus a blunt rewrite". A reader who expects the two strategies to differ in what they know about tools should be told up front that they do not; they differ in what they are told about using them.
