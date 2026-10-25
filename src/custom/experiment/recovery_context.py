"""Expose frozen repair references for one decision after a matching real tool error."""
from copy import deepcopy
import json

from .causal import text
from .memory import guidance_line, load
from .selection import digest

FILE_CASE = 'expanded-file-recovery'
PREFIX = ('\n\nRecovery reference for the observed failed call. Apply it only to repair that operation '
          'within the current request. Bind inputs and output destinations from the current request '
          'and real tool returns; this reference does not expand the task.\n')


def trigger(call):
    identity, response = call.get('semantic_identity'), call.get('response') or {}
    message = text(response)
    if identity == 'mcp-tasks::tasks_setup' and response.get('isError') and 'Unsupported file extension:' in message:
        return 'source', 'unsupported_source_extension'
    if (identity == 'mcp-tasks::tasks_add' and response.get('isError')
            and ('call tasks_setup' in message or 'call `tasks_setup`' in message)):
        return 'source', 'source_not_initialized'
    if identity == '@kazuph/mcp-taskmanager::get_next_task':
        try:
            value = json.loads(message)
        except (ValueError, TypeError):
            return None
        if isinstance(value, dict) and value.get('status') == 'error' and value.get('message') == 'Request not found':
            return 'request', 'request_id_not_found'
    return None


class RecoveryContext:
    def __init__(self, entries, aliases, workspace, context_chars, emit=None):
        self.entries = deepcopy(entries)
        self.aliases, self.workspace = aliases, workspace
        self.context_chars = context_chars
        self.emit = emit or (lambda *args: None)
        self.pending = {}
        self.activations = []

    def observe(self, call):
        matched = trigger(call)
        if not matched:
            return
        family, reason = matched
        selected, lines, length = [], [], len(PREFIX)
        for entry in self.entries:
            if entry['case_id'] != 'verified-' + family + '-workflow':
                continue
            if not set(entry['value']['tool_ids']) <= set(self.aliases):
                continue
            line = guidance_line(entry, self.aliases, self.workspace)
            if length + len(line) > self.context_chars:
                continue
            self.pending[entry['id']] = line
            selected.append(entry['id'])
            lines.append(line)
            length += len(line)
        if selected:
            activation = {'tool_call_id': call['tool_call_id'], 'semantic_identity': call['semantic_identity'],
                'trigger': reason, 'response_sha256': digest(call['response']), 'selected_ids': selected,
                'reference': PREFIX + ''.join(lines), 'lifetime': 'next_model_request_only'}
            self.activations.append(activation)
            self.emit('memory_activated', deepcopy(activation))

    def take(self):
        lines, length = [], len(PREFIX)
        for identity in sorted(self.pending):
            line = self.pending[identity]
            if length + len(line) <= self.context_chars:
                lines.append(line)
                length += len(line)
        self.pending.clear()
        return PREFIX + ''.join(lines) if lines else ''


def configure(config, tools, workspace, static_characters, emit=None):
    options = config.get('memory', {})
    if not options.get('inject') or options.get('profile', 'all') != 'error_triggered':
        return None
    artifact = load(config)
    if artifact['protocol'] != 'verified_tool_recovery_k0_v1':
        raise ValueError('Triggered recovery requires objectively verified frozen knowledge')
    aliases = {t['meta']['benchmark_semantic_identity']: t['name'] for t in tools}
    return RecoveryContext(artifact['memories'], aliases, workspace,
                           max(0, options['context_chars'] - static_characters), emit)
