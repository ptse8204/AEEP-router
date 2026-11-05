"""New task namespace and explicit small-workload ClickHouse scheduling pools."""
from copy import deepcopy
from pathlib import Path
OLD_PROJECT='aeep-langfuse-engineering-20261104'
PROJECT='aeep-langfuse-threadpool-20261104'
LABEL='com.aeep.engineering.owner'
POOL_TARGET='/etc/clickhouse-server/config.d/zz-aeep-engineering-pools.xml'
def corrected(value,work):
    result=deepcopy(value);work=Path(work);assert result['name']==OLD_PROJECT
    result['name']=PROJECT
    for name,service in result['services'].items():
        assert service['container_name']==OLD_PROJECT+'-'+name
        service['container_name']=PROJECT+'-'+name;assert service['labels'][LABEL]==OLD_PROJECT;service['labels'][LABEL]=PROJECT
        mounts=service['tmpfs'];assert isinstance(mounts,dict);service['tmpfs']=[path+':'+options for path,options in mounts.items()]
    for name,value in result['volumes'].items():
        assert value['name']==OLD_PROJECT+'-'+name;value['name']=PROJECT+'-'+name;value['labels'][LABEL]=PROJECT
    network=result['networks']['private'];assert network['name']==OLD_PROJECT+'-private';network['name']=PROJECT+'-private';network['labels'][LABEL]=PROJECT
    assert len(result['services']['minio-bucket']['volumes'])==1
    result['services']['minio-bucket']['volumes'][0]['source']=str(work/'mc')
    result['services']['clickhouse']['volumes'].append({'type':'bind','source':str(work/'clickhouse-pools.xml'),'target':POOL_TARGET,'read_only':True})
    return result
