"""Independent Shrimp practice, bounded knowledge extraction and immutable K0."""
from copy import deepcopy
from datetime import datetime, timezone
import json

from . import adapters
from .causal import normalize, text
from .core import runtime_for
from .memory import load
from .results import atomic_json, safe_error, utc_now
from .selection import ROOT, digest, file_hash, read_json
from .tool_knowledge import ORIGIN, PROTOCOL, SHRIMP, validate_artifact, verify_case, validate_value


def collect(config, directory, catalog):
    from custom.agents.tool_results import raw_result
    cases = []
    effective = deepcopy(config)
    fixtures = directory/'empty-fixtures';fixtures.mkdir()
    effective['fixtures'] = fixtures.relative_to(ROOT).as_posix()
    for index, subject in enumerate(('observatory archive', 'greenhouse irrigation')):
        for family in ('analysis','lifecycle','effect'):
            case = {'id':f'shrimp-{family}-{index}', 'family':family,
                'kind':'effect_boundary' if family=='effect' else 'procedure',
                'trace':[], 'observation':{}, 'forbidden_constants':[]}
            cases.append(case)
            with runtime_for(effective,'original',[SHRIMP],[],None) as runtime:
                current = adapters.semantic(runtime.catalog)
                if current != {k:v for k,v in catalog.items() if v['server']==SHRIMP}:
                    raise ValueError('Shrimp practice differs from the frozen Early catalog')
                def invoke(name,args):
                    key=SHRIMP+'::'+name
                    result=raw_result(runtime.call(runtime.catalog[key]['remote_name'],args))
                    call={'tool_call_id':case['id']+':'+str(len(case['trace'])),
                        'semantic_identity':key,'arguments':json.dumps(args,ensure_ascii=False),'response':result}
                    call['verification']={'kind':'contract_and_observation','response_sha256':digest(result)}
                    case['trace'].append(call)
                    atomic_json(directory/'practice.json',{'cases':cases,'status':'collecting'})
                    return call
                def state():
                    files=list((runtime.workspace/'shrimp-data').rglob('tasks.json'))
                    if len(files)!=1:raise ValueError('Expected one private Shrimp task state file')
                    return read_json(files[0])
                if family=='analysis':
                    summary=f'Design an independent {subject} prototype with validation and review stages.'
                    concept='Separate input validation, processing and reporting modules; cover invalid inputs and test the component interfaces before integration.'
                    analysis='The design separates storage from processing, has explicit input validation, and checks observable outputs through component tests.'
                    invoke('analyze_task',{'summary':summary,'initialConcept':concept})
                    invoke('reflect_task',{'summary':summary,'analysis':analysis})
                    case['observation']={'claim':'Guidance returned; no implementation completion claim'}
                    case['forbidden_constants']=[summary,concept,analysis]
                else:
                    count=1 if family=='effect' else index+2
                    names=[f'{subject} component {i+1}' for i in range(count)]
                    items=[{'name':name,'description':f'Implement and validate component {i+1} of the {subject} prototype.',
                        'implementationGuide':'Validate the current inputs, implement the requested transformation, and test observable outputs.',
                        'dependencies':[] if i==0 else [names[i-1]],'relatedFiles':[],
                        'verificationCriteria':'The requested output matches the input specification and invalid inputs are handled.'}
                        for i,name in enumerate(names)]
                    if family=='lifecycle' and index==1:
                        invoke('split_tasks',{'updateMode':'append','tasksRaw':json.dumps(items[:-1],ensure_ascii=False)})
                        existing={t['name']:t for t in state()['tasks']}
                        items[-1]['dependencies']=[existing[names[-2]]['id']]
                        invoke('split_tasks',{'updateMode':'append','tasksRaw':json.dumps(items[-1:],ensure_ascii=False)})
                    else:
                        invoke('split_tasks',{'updateMode':'append','tasksRaw':json.dumps(items,ensure_ascii=False)})
                    created=state();case['observation']['created']=created
                    by_name={t['name']:t for t in created['tasks']}
                    invoke('list_tasks',{'status':'all'})
                    if family=='lifecycle':
                        target=by_name[names[-1]]['id']
                        notes=f'Independent review note for {subject}; preserve the earlier dependency.'
                        invoke('update_task',{'taskId':target,'notes':notes})
                        case['observation']['updated']=state()
                        invoke('get_task_detail',{'taskId':target})
                        case['forbidden_constants'].append(notes)
                    else:
                        target=by_name[names[0]]['id']
                        sentinel=runtime.workspace/'boundary-result.txt'
                        case['observation']['artifact_exists_before']=sentinel.exists()
                        invoke('execute_task',{'taskId':target})
                        case['observation']['after_execute']=state()
                        case['observation']['artifact_exists_after']=sentinel.exists()
                        invoke('get_task_detail',{'taskId':target})
                        case['forbidden_constants'].append('boundary-result.txt')
                    case['forbidden_constants']+=names+[t['description'] for t in items]+[t['id'] for t in created['tasks']]
                case['trace']=normalize(case['trace'],runtime.workspace)
                case['observation']=normalize(case['observation'],runtime.workspace)
                for call in case['trace']:call['verification']['response_sha256']=digest(call['response'])
                atomic_json(directory/'practice.json',{'cases':cases,'status':'validating'})
                verify_case(case,catalog)
                atomic_json(directory/'practice.json',{'cases':cases,'status':'collecting'})
                print('Verified independent practice',case['id'],flush=True)
    return cases


def templates(cases, family):
    """Retain observed structures; replace private primitive values, including nested JSON strings."""
    first=next(c for c in cases if c['family']==family)
    mapping={};variables={}
    def variable(value,name,meaning):
        mapping[value]='${'+name+'}';variables[name]=meaning
    if family=='analysis':
        analyze=json.loads(first['trace'][0]['arguments'])
        reflect=json.loads(first['trace'][1]['arguments'])
        variable(analyze['summary'],'SUMMARY','Current project summary.')
        variable(analyze['initialConcept'],'CONCEPT','Current concrete technical approach, satisfying the exposed length constraints.')
        variable(reflect['analysis'],'ANALYSIS','Current substantive analysis to review, based on the actual request.')
    else:
        items=json.loads(json.loads(first['trace'][0]['arguments'])['tasksRaw'])
        records={t['name']:t for t in first['observation']['created']['tasks']}
        for index,item in enumerate(items,1):
            variable(item['name'],f'TASK_{index}_NAME','Current task name; adapt the example task count and dependency graph to the request.')
            variable(item['description'],f'TASK_{index}_DESCRIPTION','Current task description.')
            variable(item['implementationGuide'],f'IMPLEMENTATION_GUIDE','Current implementation steps; an example is not performed work.')
            variable(item['verificationCriteria'],'CRITERIA','Current task acceptance criteria.')
            variable(records[item['name']]['id'],f'TASK_{index}_ID','Actual existing task ID from successful split/list/detail outputs; never invent or copy practice IDs.')
        if family=='lifecycle':
            update=next(c for c in first['trace'] if c['semantic_identity'].endswith('::update_task'))
            variable(json.loads(update['arguments'])['notes'],'NOTES','Current requested task notes.')
    def generalize(value):
        if isinstance(value,dict):return {k:generalize(v) for k,v in value.items()}
        if isinstance(value,list):return [generalize(v) for v in value]
        if not isinstance(value,str):return value
        if value in mapping:return mapping[value]
        if value.startswith(('[','{')):
            return json.dumps(generalize(json.loads(value)),ensure_ascii=False)
        return value
    result=[]
    for call in first['trace']:
        # The boundary rule needs the retrieval/execution effects, not another task-creation procedure.
        if family=='effect' and call['semantic_identity'].split('::')[-1] not in ('execute_task','get_task_detail'):
            continue
        result.append({'tool_id':call['semantic_identity'],'arguments':generalize(json.loads(call['arguments'])),
                       'evidence_call_ids':[call['tool_call_id']]})
    return result,variables


def prepare(config, output):
    from .experience_state import initialize, validate_state
    from .update_provider import OpenRouterUpdater
    output=(ROOT/output).resolve()
    if not output.is_relative_to(ROOT):raise ValueError('Frozen knowledge output must stay within the project')
    source_path=output.with_name(output.stem+'.evidence.json')
    if output.exists() or source_path.exists():raise ValueError('Frozen knowledge already exists; choose a fresh output path')
    base=load(config);base_source=read_json(ROOT/config['memory']['source'])
    stamp=datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S.%fZ')
    directory=ROOT/'results'/(stamp+'_knowledge-practice');directory.mkdir(parents=True)
    journal={'protocol':PROTOCOL,'status':'collecting','created_at':utc_now(),'builds':[]}
    atomic_json(directory/'preparation.json',journal)
    try:
        cases=collect(config,directory,base['catalog'])
        entries=deepcopy(base['memories'])
        # One lifecycle observation also supports the transport constraint without a fabricated failure.
        constraint_cases=[]
        for case in cases:
            if case['family']=='lifecycle':
                item=deepcopy(case);item.update(id=case['id']+'-constraint',kind='constraint')
                constraint_cases.append(item)
        all_cases=cases+constraint_cases
        for family,kind in [('analysis','procedure'),('lifecycle','procedure'),('lifecycle','constraint'),('effect','effect_boundary')]:
            selected=[c for c in all_cases if c['family']==family and c['kind']==kind]
            call_templates,variables=templates(selected,family)
            if kind=='constraint':call_templates=[t for t in call_templates if t['tool_id'].endswith('::split_tasks')]
            refs=[c['tool_call_id'] for case in selected for c in case['trace']]
            tool_ids=sorted({t['tool_id'] for t in call_templates})
            evidence=[{'id':case['id'],'observation':case['observation'],'calls':[
                {'tool_call_id':c['tool_call_id'],'tool_id':c['semantic_identity'],'arguments':json.loads(c['arguments']),
                 'response_sha256':digest(c['response']),'response_excerpt':text(c['response'])[:1200],
                 'response_total_characters':len(text(c['response']))} for c in case['trace']]} for case in selected]
            message=('Derive concise reusable tool knowledge from independently observed practice and program readbacks. '
                'Return JSON with only content, applicability, actions (string array), verification. English. '
                'Do not copy practice names, IDs, payloads, descriptions, paths or task answers. '
                'Do not invent a failure. Explain only the selected knowledge kind: '+kind+'. '
                'Do not infer that untested input forms are forbidden. '
                'Discuss only arguments and effects of the supplied tools; do not import instructions from other tool families. '
                + ('Focus only on technical analysis and optional reflection. These tools do not take task collections or dependency references. '
                   if family=='analysis' else
                   'Focus only on retrieving execution guidance and task details, and distinguish state transitions from implemented work. '
                   if family=='effect' else
                   'Name and existing-ID dependency references were both demonstrated. Explain JSON string encoding and valid dependency representation. '
                   if kind=='constraint' else
                   'Explain creating, listing, updating and reading tasks when needed; do not require every operation for every request. '
                   'Both name and existing-ID dependency references were demonstrated. ')+
                'Observation checks establish tool effects, not general software correctness. '
                '\nTarget contracts: '+json.dumps({k:base['catalog'][k] for k in tool_ids},ensure_ascii=False)+
                '\nVerified practice: '+json.dumps(evidence,ensure_ascii=False))
            effective=deepcopy(config);effective['memory']['update_provider']['budget_usd']=0.1
            client=OpenRouterUpdater(effective,directory/'update-budget.json')
            try:
                response=client.chat.completions.create(model=config['memory']['model'],messages=[{'role':'user','content':message}],
                    max_tokens=4096,response_format={'type':'json_object'})
                if response.choices[0].finish_reason!='stop':raise ValueError('Knowledge extraction did not finish')
                def unique(pairs):
                    result={}
                    for key,value in pairs:
                        if key in result:raise ValueError('Duplicate extracted knowledge field')
                        result[key]=value
                    return result
                data=json.loads(response.choices[0].message.content or '',object_pairs_hook=unique)
                if set(data)!={'content','applicability','actions','verification'}:raise ValueError('Unexpected extracted knowledge fields')
                value=validate_value({**data,'kind':kind,'tool_ids':tool_ids,'evidence_call_ids':refs,
                    'tool_call_templates':call_templates,'template_variables':variables})
                entry={'id':digest(value)[:24],'case_id':selected[0]['id'],
                    'additional_case_ids':[c['id'] for c in selected[1:]],'value':value}
                entries.append(entry)
                journal['builds'].append({'family':family,'kind':kind,'status':'accepted','entry_id':entry['id'],
                    'independently_verified_cases':[c['id'] for c in selected],'response':response.model_dump(mode='json')})
                print('Learned',family,kind,flush=True)
            finally:client.close()
            atomic_json(directory/'preparation.json',journal)
        source={'origin':ORIGIN,'catalog':base['catalog'],'cases':deepcopy(base_source['cases'])+all_cases,
            'scope':'Independent successful practice and existing verified recovery only; no official test questions, answers or traces.',
            'parent_source_sha256':file_hash(ROOT/config['memory']['source'])}
        artifact={'protocol':PROTOCOL,'catalog':base['catalog'],'memories':entries,'memory_sha256':digest(entries),
            'source_sha256':None,'no_online_learning':True,'builder_model':config['memory']['model']}
        validate_artifact(artifact,source)
        source_path.parent.mkdir(parents=True,exist_ok=True)
        def freeze(path,value):
            # Binary UTF-8/LF keeps checksums portable through Git and Windows/macOS.
            with path.open('xb') as stream:
                stream.write((json.dumps(value,ensure_ascii=False,indent=2)+'\n').encode('utf-8'))
        freeze(source_path,source)
        artifact['source_sha256']=file_hash(source_path);freeze(output,artifact)
        updated=deepcopy(config);updated['memory'].update(artifact=output.relative_to(ROOT).as_posix(),
            source=source_path.relative_to(ROOT).as_posix(),context_chars=24000)
        state=initialize(updated,base['catalog']);validate_state(state,base['catalog'])
        profile=ROOT/'config/knowledge-evolution.json'
        if profile.exists():raise ValueError('Knowledge profile already exists')
        atomic_json(profile,updated)
        journal.update(status='completed',memory_sha256=artifact['memory_sha256'],entries=len(entries),
            output=output.relative_to(ROOT).as_posix(),profile=profile.relative_to(ROOT).as_posix())
    except Exception as exc:
        journal.update(status='failed',error=safe_error(exc));raise
    finally:atomic_json(directory/'preparation.json',journal)
    return directory,journal
