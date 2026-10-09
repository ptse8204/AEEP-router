"""Operator-only synthetic evaluator adapter; primary scheduling/grading stays in ASE."""
import argparse
import asyncio
import json
from pathlib import Path

import controlled
from definition import Inputs, digest, prepare
from verify_controlled import verify

from aeep.assessment.models import AssessmentEnvironment
from aeep_toolkit.cli import read_json
from aeep_toolkit.models import AdapterCapabilities, EvidenceBundle, SourcePin


class UpstreamFixtureAdapter:
    def __init__(self, runtime: Path, output: Path, environment: AssessmentEnvironment, inputs: Inputs):
        self.runtime, self.output, self.environment, self.inputs = runtime, output, environment, inputs
        self.plan = controlled.preview(runtime,output,environment,inputs)
        self.capabilities = AdapterCapabilities(adapter_id='agent-skill-eval.controlled-fixture',
            implementation_sha256=digest(self.plan),hosts=('fake',),candidate_types=('skill',),
            optional_invocation=True,telemetry=(),containment='unverified')

    async def evaluate(self, reviewed_plan_id: str) -> EvidenceBundle:
        if reviewed_plan_id != digest(self.plan):
            raise ValueError('exact evaluation review required')
        await controlled.execute(self.runtime,self.output,self.environment,self.inputs,reviewed_plan_id)
        verify(self.output)
        bundle=EvidenceBundle.model_validate(read_json(self.output/'toolkit-evidence.json'))
        if bundle.adapter != self.capabilities:
            raise ValueError('completed adapter binding differs from reviewed capabilities')
        return bundle


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    commands=parser.add_subparsers(dest='operation',required=True)
    for name in ('plan','run'):
        command=commands.add_parser(name)
        for option in ('candidate','suite','source','runtime','output'):
            command.add_argument('--'+option,type=Path,required=True)
        for option in ('image','docker','socket'):
            command.add_argument('--'+option,required=True)
        if name=='run':
            command.add_argument('--reviewed-digest',required=True)
    report=commands.add_parser('report')
    report.add_argument('--output',type=Path,required=True)
    args=parser.parse_args()
    if args.operation=='report':
        print(json.dumps(verify(args.output),indent=2))
        return
    inputs=prepare(args.candidate.absolute(),args.suite.absolute(),SourcePin.model_validate(read_json(args.source)))
    environment=AssessmentEnvironment(environment_id='toolkit-offline-fixture',kind='container',identity={'purpose':'upstream synthetic dispatch'},
                                     container_image=args.image,container_runtime=args.docker,container_socket=args.socket)
    adapter=UpstreamFixtureAdapter(args.runtime.resolve(),args.output.absolute(),environment,inputs)
    if args.operation=='plan':
        print(json.dumps({'review_sha256':digest(adapter.plan),'plan':adapter.plan},indent=2))
    else:
        bundle=asyncio.run(adapter.evaluate(args.reviewed_digest))
        print(json.dumps({'evidence_kind':'synthetic','trials':len(bundle.runs),'output':str(adapter.output),'live_value':'NOT_ASSESSED'}))


if __name__=='__main__':
    main()
