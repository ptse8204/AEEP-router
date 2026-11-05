"""Compose tmpfs encoding correction; mounts/options and all other fields unchanged."""
from copy import deepcopy

def corrected(value):
    result=deepcopy(value)
    for service in result['services'].values():
        mounts=service['tmpfs'];assert isinstance(mounts,dict)
        assert all(isinstance(path,str) and path.startswith('/') and isinstance(options,str) for path,options in mounts.items())
        service['tmpfs']=[path+':'+options for path,options in mounts.items()]
    return result
