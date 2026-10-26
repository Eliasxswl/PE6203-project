"""Typed tool knowledge grounded in independent successful practice."""
from copy import deepcopy
import json
from typing import Literal

from jsonschema import validate as validate_json

from .causal import call_template_schema, procedure_schema, text
from .selection import digest

PROTOCOL = 'verified_tool_knowledge_k0_v2'
ORIGIN = 'independent_verified_tool_practice'
SHRIMP = 'mcp-shrimp-task-manager'


def schema():
    from pydantic import BaseModel, Field
    Template = call_template_schema()

    class ToolKnowledge(BaseModel):
        model_config = {'extra': 'forbid'}
        kind: Literal['procedure', 'constraint', 'effect_boundary']
        tool_ids: list[str] = Field(min_length=1)
        content: str = Field(min_length=1)
        applicability: str = Field(min_length=1)
        actions: list[str] = Field(min_length=1)
        verification: str = Field(min_length=1)
        evidence_call_ids: list[str] = Field(min_length=1)
        tool_call_templates: list[Template] = Field(min_length=1)
        template_variables: dict[str, str] = Field(default_factory=dict)

    return ToolKnowledge


def validate_value(value):
    model = schema() if 'kind' in value else procedure_schema()
    return model.model_validate(value, strict=True).model_dump(mode='json', exclude_defaults=True)


def state_tasks(state):
    return {t['name']:t for t in state.get('tasks', [])}


def verify_case(case, catalog):
    """Recheck recorded arguments, responses and readback relationships, not a claimed score."""
    from custom.agents.tool_feedback import reported_error
    calls = {c['tool_call_id']:c for c in case['trace']}
    if len(calls) != len(case['trace']) or not calls:
        raise ValueError('Practice requires unique real calls')
    for call in calls.values():
        if reported_error(call['semantic_identity'],call['response']) or not text(call['response']):
            raise ValueError('Successful practice contains an error or empty observation')
        proof = call.get('verification', {})
        if proof.get('response_sha256') != digest(call['response']):
            raise ValueError('Practice response verification mismatch')
        validate_json(json.loads(call['arguments']), catalog[call['semantic_identity']]['inputSchema'])
    family = case['family']
    by_name = {c['semantic_identity'].split('::')[-1]:c for c in calls.values()}
    observation = case['observation']
    if family == 'analysis':
        if not {'analyze_task','reflect_task'} <= by_name.keys():
            raise ValueError('Analysis practice lacks observed guidance calls')
        if observation['claim'] != 'Guidance returned; no implementation completion claim':
            raise ValueError('Analysis evidence must not claim implemented work')
    elif family in ('lifecycle', 'effect'):
        items = [item for call in calls.values() if call['semantic_identity'].endswith('::split_tasks')
                 for item in json.loads(json.loads(call['arguments'])['tasksRaw'])]
        created = state_tasks(observation['created'])
        if set(created) != {t['name'] for t in items}:
            raise ValueError('Stored practice tasks do not match submitted tasks')
        for item in items:
            target = created[item['name']]
            expected = {created[ref]['id'] if ref in created else ref for ref in item.get('dependencies', [])}
            if not expected <= {t['id'] for t in created.values()}:
                raise ValueError('Practice dependency refers to an unknown task')
            if {d['taskId'] for d in target.get('dependencies', [])} != expected:
                raise ValueError('Stored dependency graph differs from the observed input')
        if family == 'lifecycle':
            update = json.loads(by_name['update_task']['arguments'])
            after = next(t for t in observation['updated']['tasks'] if t['id'] == update['taskId'])
            if after.get('notes') != update['notes']:
                raise ValueError('Task update was not persisted')
            if not all(t['id'] in text(by_name['list_tasks']['response']) for t in created.values()):
                raise ValueError('Task list did not return actual stored identifiers')
            detail = json.loads(by_name['get_task_detail']['arguments'])
            if detail['taskId'] != update['taskId'] or after['name'] not in text(by_name['get_task_detail']['response']):
                raise ValueError('Task readback is not bound to the changed record')
        else:
            execute = json.loads(by_name['execute_task']['arguments'])
            before = next(t for t in observation['created']['tasks'] if t['id'] == execute['taskId'])
            after = next(t for t in observation['after_execute']['tasks'] if t['id'] == execute['taskId'])
            if before['status'] == 'completed' or after['status'] == 'completed':
                raise ValueError('Execution guidance was incorrectly treated as completed work')
            if observation['artifact_exists_before'] or observation['artifact_exists_after']:
                raise ValueError('Effect-boundary practice unexpectedly created implementation output')
            if not text(by_name['execute_task']['response']):
                raise ValueError('Execution guidance was not observed')
    else:
        raise ValueError('Unknown successful practice family')
    return calls


def validate_artifact(artifact, source):
    if source.get('origin') != ORIGIN or source['catalog'] != artifact['catalog']:
        raise ValueError('General knowledge requires matching independent practice provenance')
    cases = {c['id']:c for c in source['cases']}
    if len(cases) != len(source['cases']):raise ValueError('Duplicate practice case identity')
    for entry in artifact['memories']:
        case = cases[entry['case_id']]
        if 'kind' not in entry['value']:
            from .recovery_memory import validate_entry
            validate_entry(entry,case,artifact['catalog'])
            continue
        value = validate_value(entry['value'])
        bound = [case]+[cases[k] for k in entry.get('additional_case_ids',[])]
        if any(c['kind'] != value['kind'] for c in bound):
            raise ValueError('Supporting evidence has a different knowledge kind')
        calls = {}
        for supporting in bound:
            observed_calls=verify_case(supporting,artifact['catalog'])
            if calls.keys() & observed_calls.keys():raise ValueError('Duplicate bound observation identity')
            calls.update(observed_calls)
        refs = set(value['evidence_call_ids'])
        observed = {c['semantic_identity'] for c in calls.values()}
        if not refs <= calls.keys() or not set(value['tool_ids']) <= observed:
            raise ValueError('Knowledge refers to unobserved evidence or tools')
        if value['kind'] != case['kind']:
            raise ValueError('Knowledge kind differs from its practice evidence')
        for template in value['tool_call_templates']:
            ids = set(template['evidence_call_ids'])
            if (not ids or not ids <= refs or template['tool_id'] not in value['tool_ids'] or
                    any(calls[i]['semantic_identity'] != template['tool_id'] for i in ids)):
                raise ValueError('Knowledge template lost its observed call binding')
        rendered = json.dumps(value,ensure_ascii=False)
        if any(token and token in rendered for supporting in bound for token in supporting['forbidden_constants']):
            raise ValueError('Knowledge copied private practice constants')


def verify_inner_json(arguments):
    """The Shrimp string transport still carries a real JSON task array."""
    if 'tasksRaw' in arguments:
        value = arguments['tasksRaw']
        if not isinstance(value,str):raise ValueError('tasksRaw must remain a JSON-encoded string')
        data = json.loads(value)
        if not isinstance(data,list) or not data or not all(isinstance(t,dict) for t in data):
            raise ValueError('tasksRaw must encode a nonempty object array')
        for task in data:
            if not isinstance(task.get('name'),str) or not isinstance(task.get('description'),str):
                raise ValueError('Shrimp task examples require string names and descriptions')
            dependencies=task.get('dependencies',[])
            if not isinstance(dependencies,list) or any(not isinstance(t,str) for t in dependencies):
                raise ValueError('Shrimp dependency references must be strings')
