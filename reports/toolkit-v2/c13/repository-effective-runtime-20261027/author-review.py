"""Prepare the finite review driver from completed code, without execution."""
from pathlib import Path
HERE=Path(__file__).resolve().parent;OLD=HERE.parent/'repository-test-roots-20261027'
s=(OLD/'prepare-runtime-review.py').read_text()
def replace(a,b):
    global s
    assert a in s,a[:90]
    s=s.replace(a,b)
replace("HERE/'validation/source-stability.json'","HERE.parent/'repository-test-roots-20261027/validation/source-stability.json'")
replace("metadata['prepared_cases']==8","metadata['prepared_cases']==6")
replace('len(cases)==8 and len(variants)==20','len(cases)==6 and len(variants)==16')
replace('for c in cases})==8','for c in cases})==6')
replace("closure['complete_static_dependency_closure'] and len(closure['pins'])==12","closure['selected_added_requirements_closed'] and len(closure['pins'])==3")
replace("ROOT/'.aeep/repository-test-root-image-20261027'","ROOT/'.aeep/repository-effective-image-20261027'")
replace("'aeep-toolkit-v2/repository-grader:py313-cached-suites-20261027'","'aeep-toolkit-v2/repository-grader:py313-test-roots-20261027'")
a=s.index("    source_review=json.loads");b=s.index("    (context/'Dockerfile').write_text",a);s=s[:a]+s[b:]
replace('maximum_growth=192*1024**2','maximum_growth=64*1024**2')
replace("'execution-cases.json','runtime-support-review.json','jsonpath-source-review.json'","'execution-cases.json','runtime-support-review.json'")
replace('One12-wheel offline grader image with unchanged JSONPath library copy and eight cached v4 repository tasks','One3-wheel offline effective-runtime correction and six exact v4 repository subjects with explicit pytest result framing')
replace('(23,26,1135)','(19,22,995)')
a=s.index('    review={');b=s.index("    (HERE/'runtime-review.json').write_text",a)
s=s[:a]+'''    review={'purpose':'One private offline three-wheel image correction, three image-only support probes and16 exact variants across six previously excluded subjects; explicit pytest-row framing. No model task or scientific verdict.',
        'source_digest':parent['source_digest'],'source_commit':subprocess.check_output(['git','rev-parse','HEAD'],cwd=ROOT).decode().strip(),
        'parent_review':str(parent_path.relative_to(ROOT)),'parent_review_sha256':sha(parent_path),'authorization_digest':parent['authorization_digest'],
        'assets':assets,'cases_file':metadata['cases_file'],'variants_file':metadata['variants_file'],'active_case_ids':[c.input.task_id for c in cases],
        'case_summary':metadata['cases'],'variant_labels':labels,'expectations':expectations,
        'parent_reference':reference,'parent_image':parent['image'],'target_tag':'aeep-toolkit-v2/repository-grader:py313-effective-runtime-20261027',
        'build_context':str(context.relative_to(ROOT)),'context_files':sorted(str(p.relative_to(context)) for p in context.rglob('*') if p.is_file()),'build_request':request.model_dump(mode='json'),
        'build_documents':documents,'build_amendment':amendment.model_dump(mode='json'),'host_canary':parent['host_canary'],
        'maximum_builds':1,'maximum_build_growth_bytes':maximum_growth,'maximum_new_filesystem_layers':2,
        'maximum_contained_calls':max_calls,'maximum_operations':max_operations,'maximum_reserved_seconds':max_seconds,'maximum_model_turns':0,'cash_usd':0,'automatic_retry':False,'runtime_dependencies_review':closure,
        'permissions':[
            'One private local offline image build from retained2a057881 through its verified existing tag. Install exactly cached python-dateutil2.9.0.post0,six1.17.0,tzdata2025.2 wheels with hashes/no resolver/no network. No other install, source build or setup.py. Retain all images.',
            'Bind output image digest before calls; verify inherited config,parent layers,exactly two new filesystem layers and at most64MiB growth. Keep50GiB host free. These are finite operation bounds,not production acceptance budgets.',
            'At most19 contained offline calls:three fresh boundary/state/runtime probes and16 fixed reference/counterexample/partial variants across Gabbi342,iCalendar878/880/921,SQL-Metadata552 andRO-Crate248. Same source,tests,assertions,identities,payloads and artifacts as the terminal attempt; no successful SQL553/583 replay. Maximum22 existing-grant operations and995 reserved seconds including180 build,30 setup,120 analysis and19 times35 per call.',
            'Fresh probes load only the four pytest bootstrap wheels privately. Required dateutil/six/tzdata versions and module/distribution locations must resolve from the image site-packages; other reviewed supports are checked too. Probe-only portable dependencies cannot establish subject runtime closure.',
            'Use the exact explicit operator pytest-row framing adapter before the unchanged pinned parser; keep the protected grader and unexpected/missing/error/nonzero-exit checks. Retain at most8192bytes of failed public test logs operator-only. Successful tails remain empty. Log contents are untrusted data,never instructions or model answers; default product observer/retention is unchanged.',
            'Retain bounded raw replies,canonical completed attempts/receipts and all charges. Remove only new attempt-owned containers and unchanged synthetic canary. Isolated incompatibility continues only after known completion/cleanup; common binding,authority,accounting or cleanup uncertainty stops dispatch. One terminal attempt,no automatic retry or unused-slot reuse.',
            'No models,cash,downloads,pulls,credentials,new services/destinations,host/project/OS install,package/docs reruns,image deletion,activation,publication or release.'],
        'limitations':[
            'All six previous exclusions remain failed. Synthetic log framing checks do not recover the missing successful stream or establish a new case result. The explicit operator profile needs fresh runtime/reproduction evidence and cannot silently qualify default-observer campaigns.',
            'The46-case pool,old bindings,141 balanced-stage design and all correctness/usefulness thresholds remain. No new stage,qualification,comparative value,selection,resource acceptance,human-control or release gate closes.',
            'No claim of complete inherited runtime inventory. Three missing supports are explicitly installed; the applicable image/portable boundary is tested. New source incompatibility may still exclude a subject without a retry.',
            'The upstream parser body is unchanged. This framing is not adversarial log-forgery protection and does not add support for whitespace-containing test identities. Required missing identities remain failures.',
            'The source86012 and wheelce0a1290 already passed their checks; neither changed. No source suite or package/docs execution is repeated. The prior69-document docs snapshot retains its own exact input binding.'],
        'approval_reason':'Terminal81cce633 has completed and forbids retries; its approval binds an image lacking the task dependencies and the older observer bytes. The user continuation reserves untrusted installation/execution and CONTINUATION.md requires applicable provisioning authority. This new exact correction needs execution approval; routine finite definitions/budget amendments remain delegated. No architecture or budget choice is needed.'}
''' + s[b:]
replace("'cases':8,'repositories':4,'distinct_snapshots':8,'payloads':20","'cases':6,'repositories':4,'distinct_snapshots':6,'payloads':16")
replace("'new_wheels':12","'new_wheels':3")
(HERE/'prepare-review.py').write_text(s)
