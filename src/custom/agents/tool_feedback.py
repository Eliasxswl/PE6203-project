"""Actionable feedback from declared contracts; no argument rewriting or extra calls."""
import json


def reported_error(identity, response):
    if response.get('isError'):
        return True
    message = '\n'.join(p.get('text', '') for p in response.get('content', []) if p.get('type') == 'text')
    if identity == 'mcp-shrimp-task-manager::split_tasks':
        return message.startswith(('tasks 參數格式錯誤', 'tasksRaw 參數格式錯誤'))
    if identity and identity.startswith('@kazuph/mcp-taskmanager::'):
        try:
            value = json.loads(message)
            return isinstance(value, dict) and value.get('status') == 'error'
        except (ValueError, TypeError):
            pass
    return False


def validation_feedback(definition, arguments, response):
    identity = (definition or {}).get('meta', {}).get('benchmark_semantic_identity')
    if not definition or not reported_error(identity, response):
        return []
    from jsonschema.validators import validator_for
    schema = definition['inputSchema']
    issues, seen = [], set()
    for error in validator_for(schema)(schema).iter_errors(arguments):
        if error.validator == 'required' and isinstance(error.instance, dict):
            for field in error.validator_value:
                path = tuple(error.absolute_path) + (field,)
                if field in error.instance or path in seen:
                    continue
                seen.add(path)
                issues.append({'argument_path': '/' + '/'.join(map(str, path)), 'constraint': 'required',
                    'field_schema': error.schema.get('properties', {}).get(field, {}),
                    'message': 'Include this missing field using the declared type and constraints.'})
        else:
            issues.append({'argument_path': '/' + '/'.join(map(str, error.absolute_path)), 'constraint': error.validator,
                           'expected': error.validator_value, 'message': error.message[:1024]})
    if identity == 'mcp-shrimp-task-manager::split_tasks' and isinstance(arguments.get('tasksRaw'), str):
        try:
            json.loads(arguments['tasksRaw'])
        except json.JSONDecodeError as exc:
            issues.append({'argument_path': '/tasksRaw', 'constraint': 'valid_json_string', 'message': str(exc),
                           'expected': 'A string containing a valid JSON array, with double-quoted keys and strings.'})
    return issues[:8]
