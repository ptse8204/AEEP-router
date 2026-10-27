"""Add one exact native-wheel data fetch to the existing metered build driver."""
from pathlib import Path
HERE=Path(__file__).resolve().parent
p=HERE/'run-bundle.py';s=p.read_text().replace('import asyncio','import asyncio\nfrom email.parser import BytesParser\nimport os\nimport zipfile')
s=s.replace("    assert {str(path.relative_to(context)) for path in context.rglob('*') if path.is_file()} == set(bundle['context_files'])",'    # The sole approved pending wheel is populated after its metered data fetch.')
needle="        operation = request.plan_id + '-runtime-build'"
assert needle in s
block='''        fetch = bundle['pending_wheel_fetch']
        cache = Path(bundle['fetch_cache']); cache.mkdir(exist_ok=False)
        fetch_records = []; verified = None
        for index in range(bundle['maximum_fetch_attempts']):
            identity = request.plan_id + '-wheel-fetch-' + str(index + 1)
            repo.reserve(request, identity, AssessmentLimits(max_operations=1, max_elapsed_seconds=120), stage='reviewed_native_wheel_fetch')
            fetch_began = time.perf_counter(); target = cache / ('attempt-' + str(index + 1) + '.partial')
            record = {'operation_id':identity, 'attempt':index + 1, 'verified':False, 'partial_retained':str(target)}
            try:
                result = subprocess.run([sys.executable, '-I', '-B', str(HERE/'fetch-reviewed-wheel.py'), str(target)],
                    cwd=ROOT, env={'PATH':os.defpath,'HOME':str(cache)}, stdin=subprocess.DEVNULL,
                    capture_output=True, text=True, timeout=90)
                record['returncode'] = result.returncode
                if result.returncode == 0:
                    facts=json.loads(result.stdout)
                    assert facts['verified'] and facts['bytes']==fetch['size_bytes'] and sha(target)==fetch['sha256']
                    record.update(verified=True,bytes=target.stat().st_size,sha256=sha(target));verified=target
            except (subprocess.TimeoutExpired, ValueError) as exc:
                record['error_type']=type(exc).__name__
            finally:
                repo.finish_operation(identity, elapsed_seconds=time.perf_counter()-fetch_began)
                fetch_records.append(record)
                with (HERE/'wheel-fetch-progress.json').open('w') as stream:json.dump(fetch_records,stream,indent=2)
            if verified is not None:break
        assert verified is not None, 'Exact data fetch unavailable; retain attempts and stop without installation'
        licenses=[]
        with zipfile.ZipFile(verified) as archive:
            metadata=next(n for n in archive.namelist() if n.endswith('.dist-info/METADATA'))
            assert archive.getinfo(metadata).file_size<1_000_000
            fields=BytesParser().parsebytes(archive.read(metadata))
            assert fields['Name'].casefold()=='scipy' and fields['Version']==fetch['version']
            requires=[r for r in fields.get_all('Requires-Dist',[]) if 'extra ==' not in r]
            assert requires==[fetch['required_runtime_dependency']]
            for name in archive.namelist():
                if '.dist-info/' not in name or 'license' not in name.casefold() or archive.getinfo(name).is_dir():continue
                assert archive.getinfo(name).file_size<=1_000_000
                assert not Path(name).is_absolute() and '..' not in Path(name).parts
                data=archive.read(name);path=cache/('license-'+str(len(licenses))+'.txt');path.write_bytes(data)
                licenses.append({'wheel_path':name,'retained':str(path),'sha256':sha(path),'bytes':len(data)})
        assert licenses, 'Retain wheel license evidence before any install'
        destination=context/fetch['filename'];assert not destination.exists();shutil.copyfile(verified,destination)
        assert sha(destination)==fetch['sha256']
        save(HERE/'wheel-fetch-result.json',{'verified':True,'artifact':str(destination),'sha256':sha(destination),'bytes':destination.stat().st_size,'licenses':licenses,'attempts':fetch_records,'executed_or_imported':False})
        assert {str(path.relative_to(context)) for path in context.rglob('*') if path.is_file()}==set(bundle['context_files'])
'''
s=s.replace(needle,block+needle)
s=s.replace("'model_turns': 0, 'downloads': 0, 'retained_image': True","'model_turns': 0, 'downloads': 1, 'retained_image': True")
p.write_text(s)
p=HERE/'derive-execution.py';s=p.read_text();needle="    derived = {key: bundle[key]"
assert needle in s
# The fetched artifact was unknown as local data before approval. Its publisher
# digest was fixed; bind the actually verified local bytes in the derived scope.
s=s.replace(needle,"    fetched=json.loads((HERE/'wheel-fetch-result.json').read_text());assert fetched['verified'] and fetched['sha256']==bundle['pending_wheel_fetch']['sha256']\n    assert sha(Path(fetched['artifact']))==fetched['sha256']\n    bundle['assets'][fetched['artifact']]=fetched['sha256']\n"+needle)
s=s.replace("maximum_operations=bundle['maximum_operations'] - 1, maximum_reserved_seconds=bundle['maximum_reserved_seconds'] - 180","maximum_operations=bundle['maximum_operations'] - 1 - len(fetched['attempts']), maximum_reserved_seconds=bundle['maximum_reserved_seconds'] - 180 - 120*len(fetched['attempts'])")
p.write_text(s)
