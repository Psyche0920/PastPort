"""Read native IDML or run explicitly granted source/photo matching without PDF parsing."""
from __future__ import annotations

import argparse
from pathlib import Path
from uuid import uuid4
from pastport_evidence.adapters.idml import IDMLDocumentReader
from pastport_evidence.application.bootstrap import atomic_write


def main() -> None:
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--idml',type=Path,required=True)
    parser.add_argument('--links',type=Path)
    parser.add_argument('--allow-missing-graphics',action='store_true',help='Keep missing source graphics as gaps; match text and available graphics only')
    mode=parser.add_mutually_exclusive_group(required=True)
    mode.add_argument('--output',type=Path,help='Local source index only; no model calls')
    mode.add_argument('--workspace',type=Path,help='Grant-bound photo matching workspace')
    parser.add_argument('--photos',type=Path)
    parser.add_argument('--grant',type=Path)
    parser.add_argument('--identity-reviews',type=Path,help='Inventory-bound distinct-object reviews for overlapping selections')
    args=parser.parse_args()
    document=IDMLDocumentReader().read(args.idml,args.links)
    if args.output:
        output: Path=args.output
        if output.exists():parser.error('Output already exists; preserve previous source versions')
        output.parent.mkdir(parents=True,exist_ok=True)
        atomic_write(output,document.model_dump_json(indent=2))
        print(f'Source imported: {len(document.stories)} stories, {len(document.pages)} layout pages, '
              f'{len(document.images)} graphics; associations remain candidates; no models called.')
        return
    if args.links is None and not args.allow_missing_graphics:
        parser.error('Matching requires --links unless --allow-missing-graphics is explicit')
    if args.photos is None or args.grant is None:
        parser.error('Paid matching requires --photos and an explicit finite --grant')
    from pastport_evidence.adapters.codex_sdk import CodexSDKTransport
    from pastport_evidence.adapters.assets import LocalAssetStore
    from pastport_evidence.application.idml_workflow import IDMLPhotoWorkflow
    from pydantic import TypeAdapter
    from pastport_evidence.application.idml_handoff import IDMLEnvironmentHandoff, DistinctIdentityReview
    from pastport_evidence.domain.execution import SubscriptionGrant
    from pastport_evidence.domain.photos import PhotoInventory
    grant=SubscriptionGrant.model_validate_json(args.grant.read_bytes())
    workspace: Path=args.workspace
    result=IDMLPhotoWorkflow(CodexSDKTransport(grant.effort)).run(args.idml,args.links,args.photos,workspace,grant,allow_missing_graphics=args.allow_missing_graphics)
    run=workspace/'runs'/(workspace/'idml-input.sha256').read_text()
    inventory=PhotoInventory.model_validate_json((run/'photo-inventory.json').read_bytes())
    identity_reviews = TypeAdapter(tuple[DistinctIdentityReview, ...]).validate_json(args.identity_reviews.read_bytes()) if args.identity_reviews else ()
    handoff=workspace/'native-handoff'
    if handoff.exists() and args.identity_reviews:
        parser.error('Reviewed handoff already exists; use a new handoff revision to preserve source bindings')
    if not handoff.exists():
        pending=workspace/('native-handoff.pending-'+uuid4().hex)
        IDMLEnvironmentHandoff().write(args.idml,args.links,document,result,inventory,LocalAssetStore(workspace/'assets'),pending,identity_reviews)
        pending.rename(handoff)
    print('Native IDML matching complete; historical and spatial approval not inferred.')


if __name__=='__main__':
    main()
