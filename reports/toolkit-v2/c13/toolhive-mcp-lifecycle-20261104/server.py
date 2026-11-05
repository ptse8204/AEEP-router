"""Reviewed first-party formatting MCP server; engineering workload, not benchmark."""
import errno,json,os,resource,signal,socket,sys
from pathlib import Path
TEXT_SCHEMA={'type':'object','properties':{'text':{'type':'string','maxLength':1024}},'required':['text'],'additionalProperties':False}
EMPTY_SCHEMA={'type':'object','properties':{},'additionalProperties':False}
TOOLS=[{'name':'format_json','description':'Format one bounded JSON value.','inputSchema':TEXT_SCHEMA},
       {'name':'boundary_probe','description':'Check only declared synthetic containment controls.','inputSchema':EMPTY_SCHEMA}]
def format_json(arguments):
    assert set(arguments)=={'text'} and isinstance(arguments['text'],str) and len(arguments['text'])<=1024
    return {'formatted':json.dumps(json.loads(arguments['text']),indent=2,sort_keys=True,allow_nan=False)}
def probe():
    note=Path('/inputs/note.txt');read=note.read_text()=='AEEP reviewed MCP input\n';denied=False
    try:note.write_text('should-not-write')
    except OSError as error:denied=error.errno in (errno.EACCES,errno.EROFS,errno.EPERM)
    network=False
    with socket.socket() as stream:
        stream.settimeout(1)
        try:stream.connect(('1.1.1.1',443))
        except OSError as error:network=error.errno in (errno.ENETUNREACH,errno.EHOSTUNREACH,errno.EACCES,errno.EPERM)
    return {'reviewed_input_read':read,'reviewed_input_write_denied':denied,'external_connect_denied':network,
            'docker_socket_absent':not Path('/var/run/docker.sock').exists(),'host_canary_absent':not Path('/Users/edwintse/Documents/aeep-toolkit-v2/.aeep/toolhive-mcp-host-canary-20261104.txt').exists(),'uid':os.getuid()}
def main():
    resource.setrlimit(resource.RLIMIT_CPU,(10,10));resource.setrlimit(resource.RLIMIT_AS,(256*1024**2,256*1024**2))
    resource.setrlimit(resource.RLIMIT_FSIZE,(1024**2,1024**2));resource.setrlimit(resource.RLIMIT_NOFILE,(64,64));resource.setrlimit(resource.RLIMIT_NPROC,(16,16));signal.alarm(150)
    for line in sys.stdin:
        if len(line)>8192:raise SystemExit(2)
        request=json.loads(line);ident=request.get('id');method=request.get('method');params=request.get('params',{})
        if ident is None:continue
        if method=='initialize':result={'protocolVersion':params['protocolVersion'],'serverInfo':{'name':'aeep-reviewed-formatting','version':'1.0'},'capabilities':{'tools':{}}}
        elif method=='ping':result={}
        elif method=='tools/list':result={'tools':TOOLS}
        elif method=='tools/call':
            try:
                value=format_json(params.get('arguments',{})) if params['name']=='format_json' else probe() if params['name']=='boundary_probe' else None
                assert value is not None;result={'content':[{'type':'text','text':json.dumps(value,allow_nan=False)}],'isError':False}
            except (AssertionError,ValueError,TypeError,KeyError):result={'content':[{'type':'text','text':'invalid reviewed tool arguments'}],'isError':True}
        else:
            print(json.dumps({'jsonrpc':'2.0','id':ident,'error':{'code':-32601,'message':'method not found'}}),flush=True);continue
        print(json.dumps({'jsonrpc':'2.0','id':ident,'result':result},allow_nan=False),flush=True)
if __name__=='__main__':main()
