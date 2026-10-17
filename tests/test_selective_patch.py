"""Offline tests for the Role 1 Selective Patch plugin."""
from copy import deepcopy
import hashlib
import json
import unittest

from custom.experiment import adapters
from custom.experiment import selective_patch


def tool(server="demo", name="read", description="Read a file", schema=None):
    return {
        "server": server,
        "name": name,
        "description": description,
        "inputSchema": schema if schema is not None else {
            "type": "object",
            "properties": {"path": {"type": "string", "description": "Path"}},
            "required": ["path"],
        },
    }


def catalog(*tools):
    return {f"{item['server']}::{item['name']}": item for item in tools}


def stable_hash(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(",", ":")).encode()).hexdigest()


class SelectivePatchTests(unittest.TestCase):
    def patch(self, knowledge, old, new):
        return selective_patch.selective_patch(knowledge, old, new, {"stage": "iter3"})

    def test_registered_with_adapter_contract(self):
        old = catalog(tool())
        result = adapters.update("selective_patch", deepcopy(old), old, old, {"stage": "iter3"})
        self.assertEqual(result["changed_entries"], [])
        self.assertEqual(result["api_calls"], 0)
        self.assertEqual(result["cost_basis"], "Deterministic local schema comparison; no model requests")

    def test_identical_catalog_preserves_all_tools(self):
        old = catalog(tool(), tool("demo", "write", "Write a file"))
        result = self.patch(deepcopy(old), old, old)
        self.assertEqual(result.knowledge, old)
        self.assertEqual(result.changed_entries, [])
        self.assertIn("2 unchanged shared entries preserved", result.explanation)

    def test_description_only_change(self):
        old = catalog(tool())
        new = catalog(tool(description="Read text from a local file"))
        result = self.patch(deepcopy(old), old, new)
        change = result.changed_entries[0]
        self.assertEqual(change["change_type"], "DESC")
        self.assertEqual(change["operations"], [{"path": "/description", "operation": "replace"}])
        self.assertEqual(result.knowledge["demo::read"]["description"], new["demo::read"]["description"])
        self.assertEqual(result.knowledge["demo::read"]["inputSchema"], old["demo::read"]["inputSchema"])

    def test_parameter_addition_and_removal(self):
        old = catalog(tool())
        added_schema = deepcopy(old["demo::read"]["inputSchema"])
        added_schema["properties"]["encoding"] = {"type": "string", "default": "utf-8"}
        new = catalog(tool(schema=added_schema))
        added = self.patch(deepcopy(old), old, new)
        self.assertEqual(added.changed_entries[0]["change_type"], "PARAM")
        self.assertIn({"path": "/inputSchema/properties/encoding", "operation": "add"},
                      added.changed_entries[0]["operations"])

        removed = self.patch(deepcopy(new), new, old)
        self.assertIn({"path": "/inputSchema/properties/encoding", "operation": "remove"},
                      removed.changed_entries[0]["operations"])
        self.assertNotIn("encoding", removed.knowledge["demo::read"]["inputSchema"]["properties"])

    def test_parameter_type_and_required_changes(self):
        old = catalog(tool())
        schema = deepcopy(old["demo::read"]["inputSchema"])
        schema["properties"]["path"]["type"] = "array"
        schema["required"] = []
        new = catalog(tool(schema=schema))
        result = self.patch(deepcopy(old), old, new)
        operations = result.changed_entries[0]["operations"]
        self.assertIn({"path": "/inputSchema/properties/path/type", "operation": "replace"}, operations)
        self.assertIn({"path": "/inputSchema/required", "operation": "replace"}, operations)
        self.assertEqual(result.changed_entries[0]["change_type"], "PARAM")

    def test_enum_default_and_items_changes(self):
        old_schema = {
            "type": "object",
            "properties": {
                "format": {"type": "string", "enum": ["text", "json"], "default": "text"},
                "paths": {"type": "array", "items": {"type": "string"}},
            },
        }
        old = catalog(tool(schema=old_schema))
        new_schema = deepcopy(old_schema)
        new_schema["properties"]["format"]["enum"] = ["text", "json", "yaml"]
        new_schema["properties"]["format"]["default"] = "yaml"
        new_schema["properties"]["paths"]["items"] = {"type": "object"}
        new = catalog(tool(schema=new_schema))
        result = self.patch(deepcopy(old), old, new)
        operations = result.changed_entries[0]["operations"]
        self.assertIn({"path": "/inputSchema/properties/format/enum", "operation": "replace"}, operations)
        self.assertIn({"path": "/inputSchema/properties/format/default", "operation": "replace"}, operations)
        self.assertIn({"path": "/inputSchema/properties/paths/items/type", "operation": "replace"}, operations)
        self.assertEqual(result.changed_entries[0]["change_type"], "PARAM")

    def test_nested_schema_change(self):
        old_schema = {
            "type": "object",
            "properties": {
                "options": {
                    "type": "object",
                    "properties": {"limit": {"type": "integer", "default": 10}},
                }
            },
        }
        old = catalog(tool(schema=old_schema))
        new_schema = deepcopy(old_schema)
        new_schema["properties"]["options"]["properties"]["limit"]["default"] = 25
        new = catalog(tool(schema=new_schema))
        result = self.patch(deepcopy(old), old, new)
        self.assertIn(
            {"path": "/inputSchema/properties/options/properties/limit/default", "operation": "replace"},
            result.changed_entries[0]["operations"],
        )
        self.assertEqual(result.knowledge["demo::read"]["inputSchema"], new_schema)

    def test_tool_addition_and_removal(self):
        old = catalog(tool())
        new = catalog(tool(), tool("demo", "write", "Write a file"))
        added = self.patch(deepcopy(old), old, new)
        self.assertIn("demo::write", added.knowledge)
        self.assertEqual(added.changed_entries[0]["change_type"], "TOOL")
        self.assertEqual(added.changed_entries[0]["operations"], [{"path": "/", "operation": "add"}])

        removed = self.patch(deepcopy(new), new, old)
        self.assertNotIn("demo::write", removed.knowledge)
        self.assertEqual(removed.changed_entries[0]["operations"], [{"path": "/", "operation": "remove"}])

    def test_mixed_description_and_schema_change(self):
        old = catalog(tool())
        schema = deepcopy(old["demo::read"]["inputSchema"])
        schema["properties"]["path"]["type"] = "array"
        new = catalog(tool(description="Read one or more files", schema=schema))
        result = self.patch(deepcopy(old), old, new)
        self.assertEqual(result.changed_entries[0]["change_type"], "MIXED")

    def test_unchanged_entries_are_byte_equivalent_in_content(self):
        unchanged = tool("demo", "keep", "Do not alter")
        old = catalog(tool(), unchanged)
        schema = deepcopy(old["demo::read"]["inputSchema"])
        schema["properties"]["path"]["type"] = "array"
        new = catalog(tool(schema=schema), deepcopy(unchanged))
        before = stable_hash(old["demo::keep"])
        result = self.patch(deepcopy(old), old, new)
        self.assertEqual(stable_hash(result.knowledge["demo::keep"]), before)
        self.assertEqual(result.knowledge["demo::keep"], old["demo::keep"])

    def test_inputs_are_not_mutated_and_results_are_deterministic(self):
        old = catalog(tool())
        new = catalog(tool(description="Updated description"))
        knowledge = deepcopy(old)
        before = deepcopy((knowledge, old, new))
        first = self.patch(knowledge, old, new)
        second = self.patch(deepcopy(knowledge), old, new)
        self.assertEqual((knowledge, old, new), before)
        self.assertEqual(first.knowledge, second.knowledge)
        self.assertEqual(first.changed_entries, second.changed_entries)

    def test_reapplying_same_patch_is_idempotent(self):
        old = catalog(tool())
        schema = deepcopy(old["demo::read"]["inputSchema"])
        schema["properties"]["encoding"] = {"type": "string"}
        new = catalog(tool(description="Updated", schema=schema))
        first = self.patch(deepcopy(old), old, new)
        second = self.patch(first.knowledge, old, new)
        self.assertEqual(second.knowledge, first.knowledge)


if __name__ == "__main__":
    unittest.main()
