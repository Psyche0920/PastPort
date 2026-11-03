"""Localize native IDML mappings using an explicitly authorized environment grant."""
from __future__ import annotations
import argparse
from pathlib import Path
from pastport_matched_environment.adapters.codex_sdk import CodexSDKTransport
from pastport_matched_environment.application.idml_environment import IDMLEnvironmentWorkflow
from pastport_matched_environment.domain.execution import SubscriptionGrant


def main() -> None:
    parser=argparse.ArgumentParser(description=__doc__)
    for name in ('handoff','tour','workspace','grant'):
        parser.add_argument('--'+name,type=Path,required=True)
    parser.add_argument('--run-id',required=True)
    args=parser.parse_args()
    grant=SubscriptionGrant.model_validate_json(args.grant.read_bytes())
    output=IDMLEnvironmentWorkflow(CodexSDKTransport(grant.effort)).run(args.handoff,args.tour,args.workspace,args.run_id,grant)
    print(output)


if __name__=='__main__':
    main()
