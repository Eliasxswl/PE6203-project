from copy import deepcopy
import json
import unittest

from jsonschema import ValidationError

from custom.experiment.update_contract import response_format, parse, normalize_optionals


def wire_record(entry, catalog):
    """Test provider output includes explicit nulls for absent optional arguments."""
    from custom.experiment.experience_state import submission
    record = submission(entry)
    def fill(value, schema):
        if isinstance(value, dict):
            return {key: fill(value[key], child) if key in value else None
                    for key, child in schema.get('properties', {}).items()}
        if isinstance(value, list):
            return [fill(v, schema.get('items', {})) for v in value]
        return value
    for call in record['calls'].values():
        call['arguments'] = fill(call['arguments'], catalog[call['tool_id']]['inputSchema'])
    return {'result': record}


class UpdateContractTests(unittest.TestCase):
    def setUp(self):
        self.key = 'shrimp::split_tasks'
        self.catalog = {self.key: {'inputSchema': {'type':'object', 'properties': {
            'tasksRaw': {'type':'string'}, 'count': {'type':'integer'},
            'nullable': {'type':['string','null']}}, 'required':['tasksRaw'],
            'additionalProperties':False}}}
        self.record = {'tool_ids':[self.key], 'kind':'constraint', 'content':'Keep encoded tasks.',
            'applicability':'On splitting.', 'actions':['Serialize the array.'], 'verification':'Read back.',
            'calls':{'call_0':{'tool_id':self.key,'arguments':{'tasksRaw':'[]'}}}}
        self.contract = response_format(self.record,self.catalog)
        self.wire = {'result':deepcopy(self.record)}
        self.wire['result']['calls']['call_0']['arguments'].update(count=None,nullable=None)

    def test_all_object_fields_are_closed_and_required(self):
        def walk(s):
            if isinstance(s,dict):
                if s.get('type')=='object':
                    self.assertIs(s['additionalProperties'],False)
                    self.assertEqual(set(s['required']),set(s['properties']))
                for v in s.values():walk(v)
            elif isinstance(s,list):
                for v in s:walk(v)
        walk(self.contract['json_schema']['schema'])
        self.assertTrue(self.contract['json_schema']['strict'])

    def test_json_string_stays_string_and_nullable_semantics_are_preserved(self):
        nested=json.dumps([{'name':'${TASK_NAME}','description':'Quote: "alpha"'}])
        self.wire['result']['calls']['call_0']['arguments']['tasksRaw']=nested
        result=parse(json.dumps(self.wire),self.contract,self.catalog)
        args=result['calls']['call_0']['arguments']
        self.assertEqual(args['tasksRaw'],nested)
        self.assertNotIn('count',args)
        self.assertIn('nullable',args)
        self.assertIsNone(args['nullable'])

    def test_wrong_container_extra_fields_and_missing_slots_are_rejected(self):
        cases=[]
        bad=deepcopy(self.wire);bad['result']['calls']['call_0']['arguments']['tasksRaw']=[];cases.append(bad)
        bad=deepcopy(self.wire);bad['result']['calls']['call_1']={};cases.append(bad)
        bad=deepcopy(self.wire);bad['result']['calls']={};cases.append(bad)
        bad=deepcopy(self.wire);bad['result']['evidence_call_ids']=[];cases.append(bad)
        for bad in cases:
            with self.subTest(bad=bad),self.assertRaises(ValidationError):
                parse(json.dumps(bad),self.contract,self.catalog)

    def test_concatenated_duplicate_and_nonfinite_json_are_not_salvaged(self):
        raw=json.dumps(self.wire)
        for bad in [raw+'\n'+raw, '{"result":{},"result":{}}', '{"result":NaN}']:
            with self.subTest(bad=bad),self.assertRaises(ValueError):
                parse(bad,self.contract,self.catalog)

    def test_primitive_variables_and_explicit_unavailable_variant(self):
        self.wire['result']['calls']['call_0']['arguments']['count']='${COUNT}'
        result=parse(json.dumps(self.wire),self.contract,self.catalog)
        self.assertEqual(result['calls']['call_0']['arguments']['count'],'${COUNT}')
        missing={'unavailable':True,'reason':'Required operation was removed.'}
        self.assertEqual(parse(json.dumps({'result':missing}),self.contract,self.catalog),missing)

    def test_recursive_null_transport_does_not_drop_required_or_legitimate_null(self):
        schema={'type':'object','properties':{'a':{'type':'array','items':{'type':'object',
            'properties':{'required':{'type':'null'},'optional':{'type':'string'}},'required':['required']}}}}
        self.assertEqual(normalize_optionals({'a':[{'required':None,'optional':None}]},schema),
                         {'a':[{'required':None}]})


if __name__=='__main__':unittest.main()
