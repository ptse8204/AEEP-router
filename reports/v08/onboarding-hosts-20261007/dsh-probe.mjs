import {Context} from '@deepseek-ai/cordis';
import SystemPrompt from '@deepseek-ai/dsh-system-prompt';
import ToolRegistry from '@deepseek-ai/dsh-tools';
import * as mcp from '@deepseek-ai/dsh-mcp-client';
import {readFileSync,writeFileSync} from 'node:fs';
import {execFileSync} from 'node:child_process';
import assert from 'node:assert/strict';
const py='/tmp/aeep-onboarding-continuation/mac-final/home/data/venv/bin/python';
const root='/tmp/aeep-host-checks-20261007/dsh';
const env={PATH:process.env.PATH,HOME:root+'/home',AEEP_CONFIG_HOME:root+'/home/aeep'};
for(const key of Object.keys(process.env))delete process.env[key];Object.assign(process.env,env);
execFileSync(py,['-c',`from pathlib import Path; from aeep.onboarding import initialize,connect; from aeep.access import change_access; p=Path('${root}/project');p.mkdir(parents=True,exist_ok=True); initialize();connect('alpha','dsh',p);connect('beta','dsh',p);change_access('beta','aeep_discovery_status',False)`],{env});
const config=JSON.parse(readFileSync(root+'/project/.aeep/dsh-connection.json')).flatMap(p=>p.insert);
const ctx=new Context();const fibers=[];const record={packages:JSON.parse(readFileSync(new URL('./package-lock.json',import.meta.url))).packages,checks:[]};
const change=(allow)=>execFileSync(py,['-c',`from aeep.access import change_access;change_access('alpha','aeep_discovery_status',${allow?'True':'False'})`],{env});
async function mount(plugin,cfg){const fiber=ctx.plugin(plugin,cfg);fibers.push(fiber);await fiber.inertia;return fiber;}
try{
 await mount(SystemPrompt,{});await mount(ToolRegistry,{});
 let alpha=await mount(mcp,{...config[0].config,cwd:root+'/project',failOnStartupError:true});await mount(mcp,{...config[1].config,cwd:root+'/project',failOnStartupError:true});
 const name='mcp__'+config[0].config.serverName+'__aeep_discovery_status';const beta='mcp__'+config[1].config.serverName+'__aeep_discovery_status';
 record.initial=ctx.tools.schemas().map(t=>t.name);assert(record.initial.includes(name));assert(!record.initial.includes(beta));record.checks.push('actual Cordis tools service receives distinct server inventories');
 const call=()=>ctx.tools.execute({callId:'check-'+Date.now(),name,arguments:{},signal:new AbortController().signal});
 record.call=await call();assert(!record.call.isError);change(false);record.denied=await call();assert(record.denied.isError);record.checks.push('actual DSH dispatch succeeds then rejects stale declaration after revocation');
 await alpha.dispose();alpha=await mount(mcp,{...config[0].config,cwd:root+'/project',failOnStartupError:true});record.reloaded=ctx.tools.schemas().map(t=>t.name);assert(!record.reloaded.includes(name));change(true);await alpha.dispose();alpha=await mount(mcp,{...config[0].config,cwd:root+'/project',failOnStartupError:true});assert(ctx.tools.schemas().some(t=>t.name===name));assert(!ctx.tools.schemas().some(t=>t.name===beta));record.checks.push('reload hides denied tool; restore keeps other connection denied');record.status='passed';
}catch(e){record.status='failed';record.error=String(e);process.exitCode=1;}finally{for(const f of fibers.reverse())await f.dispose();delete record.packages;writeFileSync('/Users/edwintse/Documents/aeep-agent-router/reports/v08/onboarding-hosts-20261007/dsh-result.json',JSON.stringify(record,null,2)+'\n');console.log(record);}
