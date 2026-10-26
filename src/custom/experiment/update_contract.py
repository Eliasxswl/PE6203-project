"""Strict transport contract for symbolic knowledge updates; tool schemas remain authoritative."""
from copy import deepcopy
import json

from jsonschema import Draft202012Validator


PROTOCOL = 'json_schema_named_calls_v2'
PLACEHOLDER = {'type': 'string', 'pattern': r'^\$\{[A-Z][A-Z0-9_]*\}$'}


def closed(properties):
    return {'type': 'object', 'properties': properties, 'required': list(properties),
            'additionalProperties': False}


def symbolic_schema(schema):
    """Require explicit nullable optional fields; allow primitive symbolic bindings only."""
    if '$ref' in schema:
        raise ValueError('Resolve target schema references before building an updater contract')
    if 'anyOf' in schema or 'oneOf' in schema:
        return {'anyOf': [symbolic_schema(s) for s in schema.get('anyOf', schema.get('oneOf'))]}
    kind = schema.get('type')
    if isinstance(kind, list):
        return {'anyOf': [symbolic_schema({**schema, 'type': t}) for t in kind]}
    if kind == 'object' or 'properties' in schema:
        properties = {}
        for key, value in schema.get('properties', {}).items():
            item = symbolic_schema(value)
            if key not in schema.get('required', []):
                item = {'anyOf': [item, {'type': 'null'}]}
            properties[key] = item
        return closed(properties)
    if kind == 'array':
        return {'type': 'array', 'items': symbolic_schema(schema.get('items', {}))}
    if kind not in ('string', 'integer', 'number', 'boolean', 'null'):
        raise ValueError('Updater target arguments require explicit JSON types')
    primitive = {'type': kind}
    if 'enum' in schema:
        primitive['enum'] = deepcopy(schema['enum'])
    if 'const' in schema:
        primitive['enum'] = [schema['const']]
    return primitive if kind == 'null' else {'anyOf': [primitive, deepcopy(PLACEHOLDER)]}


def response_format(record, catalog):
    text = {'type': 'string', 'minLength': 1}
    properties = {}
    for key, value in record.items():
        if key == 'calls':
            calls = {}
            for slot, call in value.items():
                keys = [call['tool_id']] if call['tool_id'] in catalog else sorted(catalog)
                variants = [closed({'tool_id': {'type': 'string', 'enum': [key]},
                    'arguments': symbolic_schema(catalog[key]['inputSchema'])}) for key in keys]
                if not variants:
                    raise ValueError('No target tool can represent the learned call slot')
                calls[slot] = variants[0] if len(variants) == 1 else {'anyOf': variants}
            properties[key] = closed(calls)
        elif key == 'tool_ids':
            properties[key] = {'type': 'array', 'items': {'type': 'string', 'enum': sorted(catalog)}, 'minItems': 1}
        elif key == 'kind':
            properties[key] = {'type': 'string', 'enum': [value]}
        elif isinstance(value, list):
            properties[key] = {'type': 'array', 'items': deepcopy(text), 'minItems': 1}
        elif isinstance(value, str):
            properties[key] = deepcopy(text)
        else:
            raise ValueError('Unsupported knowledge value in updater output contract')
    schema = closed({'result': {'anyOf': [closed(properties), closed({
        'unavailable': {'type': 'boolean', 'enum': [True]}, 'reason': deepcopy(text)})]}})
    Draft202012Validator.check_schema(schema)
    return {'type': 'json_schema', 'json_schema': {
        'name': 'tool_knowledge_update', 'strict': True, 'schema': schema}}


def _allows_null(schema):
    return schema.get('type') == 'null' or (isinstance(schema.get('type'), list)
        and 'null' in schema['type']) or any(_allows_null(s) for s in schema.get('anyOf', schema.get('oneOf', [])))


def normalize_optionals(value, schema):
    """Decode transport null-as-absent only for optional fields that disallow actual null."""
    if isinstance(value, dict):
        result = {}
        for key, item in value.items():
            child = schema.get('properties', {}).get(key, {})
            if item is None and key not in schema.get('required', []) and not _allows_null(child):
                continue
            result[key] = normalize_optionals(item, child)
        return result
    if isinstance(value, list):
        return [normalize_optionals(item, schema.get('items', {})) for item in value]
    return value


def parse(content, contract, catalog):
    def unique(pairs):
        result = {}
        for key, value in pairs:
            if key in result:
                raise ValueError('Duplicate experience-update JSON key')
            result[key] = value
        return result
    def reject_constant(value):
        raise ValueError('Non-finite experience-update JSON number: ' + value)
    data = json.loads(content, object_pairs_hook=unique, parse_constant=reject_constant)
    Draft202012Validator(contract['json_schema']['schema']).validate(data)
    result = data['result']
    for call in result.get('calls', {}).values():
        call['arguments'] = normalize_optionals(call['arguments'], catalog[call['tool_id']]['inputSchema'])
    return result
