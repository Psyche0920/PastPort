"""Bounded research, revision and professional review within the existing graph nodes."""

from functools import partial
from typing import TYPE_CHECKING

from pastport.application.models import RunRecord, ServiceError, StoredArtifact
from pastport.application.story_editing import story_field_hash
from pastport.application.updates import updated
from pastport.application.workflow_control import ResearchRound, RevisionRound
from pastport.domain.common import (
    ArtifactKind,
    ArtifactRef,
    CanonicalSerializer,
    Contract,
    VersionedPayload,
)
from pastport.domain.evidence import Coverage, EvidencePackage, SourceIndexDraft
from pastport.domain.modules import (
    DraftRequest,
    EvidenceFindings,
    ModuleResult,
    NarrativeDraft,
    NarrativeReview,
    NarrativeReviewRequest,
    ResearchRequest,
    ReviseRequest,
    RevisionRequest,
)
from pastport.domain.workflow import NodeName

if TYPE_CHECKING:
    from pastport.workflow.stages import StageRunner


class BranchRunner:
    def __init__(self, stages: "StageRunner") -> None:
        self.stages = stages

    def store(self, run: RunRecord, message: str, **changes: object) -> RunRecord:
        result = updated(run, state=updated(run.state, revision=run.state.revision + 1), **changes)
        self.stages.database.save(result, run.state.revision, message)
        return result

    def research(self, run: RunRecord) -> None:
        stages = self.stages
        port = stages.evidence
        if port is None:
            raise ServiceError(
                "MODULE_NOT_CONFIGURED", "Evidence adapter is required by research_evidence"
            )
        selected = run.selected_candidate
        if selected is not None:
            stages.authority.actor(selected.actor_id, run.state.project_id, "narrative")
        rounds = run.control.research_rounds
        active = rounds[-1] if rounds and not rounds[-1].completed else None
        if active is None:
            if run.state.research_rounds_started >= 2:
                # Reuse complete direction findings without another research call.
                reusable = next(
                    (
                        f
                        for r in reversed(rounds)
                        for f in reversed(r.findings)
                        if selected
                        and not run.control.pending_research
                        and r.completed
                        and not f.unresolved_items
                        and len(f.route_candidates) == 1
                        and f.route_candidates[0].candidate_id == selected.candidate_id
                    ),
                    None,
                )
                if reusable is not None:
                    self.evidence_package(run, reusable)
                else:
                    stages.router.stop(
                        run,
                        "RESEARCH_LIMIT",
                        "No complete direction evidence remains within the two-round limit",
                    )
                return
            requests = run.control.pending_research
            if not requests:
                requests = (
                    stages.router.research_question(
                        run, "Establish the selected story premises and route.", ()
                    ),
                )
            stages.router.check_research(run, requests)
            number = run.state.research_rounds_started + 1
            active = ResearchRound(
                round_id="research-" + str(number),
                requests=requests,
                index=stages.load(run, "index", SourceIndexDraft),
            )
            started = updated(
                run,
                control=updated(run.control, research_rounds=(*rounds, active)),
                state=updated(
                    run.state, revision=run.state.revision + 1, research_rounds_started=number
                ),
            )
            stages.database.save(started, run.state.revision, "Research round manifest frozen")
            run = started
        previous = tuple(f for r in run.control.research_rounds[:-1] for f in r.findings)
        for position in range(len(active.findings), len(active.requests)):
            question = active.requests[position]
            request = ResearchRequest(
                index=active.index,
                evidence_request=question,
                selected_candidate=selected,
                existing_findings=(*previous, *active.findings),
            )
            response = stages.call(
                run,
                ModuleResult[EvidenceFindings],
                partial(port.research, request),
                request=request,
                unit=active.round_id + "-" + str(position),
            )
            if response.payload is not None:
                self.check_findings(run, response.payload, question.request_id)
            if response.outcome != "completed":
                if response.outcome != "blocked":
                    active = updated(active, completed=True)
                    run = updated(
                        run,
                        control=updated(
                            run.control, research_rounds=(*run.control.research_rounds[:-1], active)
                        ),
                    )
                if response.payload is not None:
                    run = self.append(run, active.round_id + "-partial", "report", response.payload)
                if response.outcome == "changes_required":
                    question = updated(
                        question,
                        request_id="research-change-" + str(run.state.revision),
                        question=response.reason,
                        reason=response.reason,
                        affected_ids=response.changed_ids,
                        required_evidence=(response.reason,),
                    )
                    stages.router.research(run, (question,), run.control.research_return_action)
                else:
                    stages.completed(run, response)
                return
            assert response.payload is not None
            active = updated(active, findings=(*active.findings, response.payload))
            run = self.store(
                run,
                "Research question result saved",
                control=updated(
                    run.control, research_rounds=(*run.control.research_rounds[:-1], active)
                ),
            )
        active = updated(active, completed=True)
        run = updated(
            run,
            control=updated(
                run.control,
                research_rounds=(*run.control.research_rounds[:-1], active),
                pending_research=(),
            ),
        )
        findings = active.findings[-1]
        # Every later result must carry forward earlier results, so no question disappears.
        for earlier in active.findings[:-1]:
            if not {CanonicalSerializer.digest(c) for c in earlier.claims} <= {
                CanonicalSerializer.digest(c) for c in findings.claims
            } or not {CanonicalSerializer.digest(a) for a in earlier.assets} <= {
                CanonicalSerializer.digest(a) for a in findings.assets
            }:
                raise ServiceError(
                    "RESEARCH_OUTPUT_INVALID",
                    "Research results must retain earlier question findings",
                )
        if active.requests[0].purpose == "scope_gap":
            run = self.append(run, active.round_id, "report", findings)
            stages.save_artifact(
                run,
                "index",
                "source_index",
                findings.index,
                "discover_story",
                index_ref=self.ref(run, "index", "source_index", findings.index),
                pending_request_id=None,
            )
        else:
            self.evidence_package(run, findings)

    @staticmethod
    def check_findings(run: RunRecord, findings: EvidenceFindings, request_id: str) -> None:
        if findings.request_id != request_id or findings.index.project_id != run.state.project_id:
            raise ServiceError(
                "RESEARCH_OUTPUT_INVALID", "Findings do not match their project and question"
            )
        old = next(
            a
            for a in reversed(run.artifacts)
            if a.reference.artifact_id == run.state.run_id + ":index"
        )
        index = SourceIndexDraft.model_validate_json(old.payload_json)
        if findings.index.source_folder_id != index.source_folder_id or {
            site.site_id for site in findings.index.sites
        } != {site.site_id for site in index.sites}:
            raise ServiceError(
                "RESEARCH_SCOPE_INVALID", "Research changed registered project targets"
            )
        if findings.sources != findings.index.sources:
            raise ServiceError(
                "RESEARCH_OUTPUT_INVALID", "Findings sources must match the updated index"
            )
        for route in findings.route_candidates:
            if route.project_id != run.state.project_id:
                raise ServiceError("PROJECT_MISMATCH", "Research returned a cross-project route")

    def evidence_package(self, run: RunRecord, findings: EvidenceFindings) -> None:
        stages = self.stages
        selected = run.selected_candidate
        if selected is None:
            raise ServiceError("SELECTION_MISSING", "Evidence package needs a confirmed direction")
        routes = findings.route_candidates
        project = stages.database.project(run.state.project_id)
        if len(routes) != 1 or len(routes[0].ordered_places) != 1:
            raise ServiceError(
                "CAPABILITY_UNSUPPORTED", "This integration requires one explicit single-site route"
            )
        route = routes[0]
        if route.unknowns:
            stages.router.stop(
                run,
                "ROUTE_REVIEW_REQUIRED",
                "Resolve the reported route unknowns before evidence handoff",
            )
            return
        if route.candidate_id != selected.candidate_id:
            raise ServiceError(
                "RESEARCH_OUTPUT_INVALID", "Route must resolve the selected direction"
            )
        old_index = stages.load(run, "index", SourceIndexDraft)
        if findings.index.source_folder_id != old_index.source_folder_id or {
            site.site_id for site in findings.index.sites
        } != {site.site_id for site in old_index.sites}:
            raise ServiceError(
                "RESEARCH_SCOPE_INVALID", "Research changed the registered project scope"
            )
        route_ref = self.ref(run, "route", "route", route)
        evidence = EvidencePackage(
            project_id=run.state.project_id,
            schema_version="0.1.0",
            content_version="research-" + str(run.state.research_rounds_started),
            source_folder_id=project.folder_id,
            scope=tuple(site.site_id for site in findings.index.sites),
            sources=findings.sources,
            sites=findings.index.sites,
            claims=findings.claims,
            assets=findings.assets,
            spatial_edges=(),
            route_refs=(route_ref,),
            coverage=tuple(
                Coverage(
                    site_id=site.site_id,
                    disposition="main",
                    reason="Proposed scope awaiting evidence review",
                )
                for site in findings.index.sites
            ),
            unresolved_items=findings.unresolved_items,
        )
        run = self.append(run, "index", "source_index", findings.index)
        run = self.append(run, "route", "route", route)
        run = updated(
            run,
            review_requests=(),
            control=updated(
                run.control,
                action="revise" if run.control.research_return_action == "revise" else "draft",
            ),
        )
        stages.save_artifact(
            run,
            "evidence",
            "evidence",
            evidence,
            "evidence_review",
            evidence_ref=self.ref(run, "evidence", "evidence", evidence),
            index_ref=self.ref(run, "index", "source_index", findings.index),
            approved_route_ref=None,
            pending_review_id=None,
            pending_request_id=None,
            runtime_ref=None,
        )

    def narrative(self, run: RunRecord) -> None:
        stages = self.stages
        port = stages.narrative
        if port is None:
            raise ServiceError(
                "MODULE_NOT_CONFIGURED", "Narrative adapter is required by draft_narrative"
            )
        if run.selected_candidate is None:
            raise ServiceError("SELECTION_MISSING", "Direction missing")
        project = stages.database.project(run.state.project_id)
        request = DraftRequest(
            evidence=stages.evidence_view(run),
            selected_candidate=run.selected_candidate,
            requirements=project.requirements,
            runtime_capabilities=stages.capabilities,
            locked_fields=run.locked_fields,
        )
        action = run.control.action
        previous = self.previous(run)
        if action == "review":
            if previous is None:
                raise ServiceError("ARTIFACT_MISSING", "Professional review needs a draft")
            review_request = NarrativeReviewRequest(
                narrative=previous,
                evidence=request.evidence,
                requirements=project.requirements,
                runtime_capabilities=stages.capabilities,
            )
            reviewed = stages.call(
                run,
                ModuleResult[NarrativeReview],
                lambda context: port.review(review_request, context),
                request=review_request,
                unit=run.control.review_request_id or "review",
            )
            self.review_result(run, reviewed)
            return
        if action == "revise":
            if previous is None or run.control.revision_request is None:
                raise ServiceError(
                    "REVISION_REQUEST_INVALID", "Revision needs a current draft and feedback"
                )
            rounds = run.control.revision_rounds
            active = rounds[-1] if rounds and not rounds[-1].completed else None
            if active is None:
                if run.state.narrative_revisions_started >= 2:
                    stages.router.stop(
                        run, "REVISION_LIMIT", "The two narrative revision rounds are exhausted"
                    )
                    return
                number = run.state.narrative_revisions_started + 1
                active = RevisionRound(
                    round_id="revision-" + str(number), request=run.control.revision_request
                )
                started = updated(
                    run,
                    control=updated(run.control, revision_rounds=(*rounds, active)),
                    state=updated(
                        run.state,
                        revision=run.state.revision + 1,
                        narrative_revisions_started=number,
                    ),
                )
                stages.database.save(
                    started, run.state.revision, "Narrative revision manifest frozen"
                )
                run = started
            revise_request = ReviseRequest(
                draft_request=request,
                narrative=previous,
                revision_request=active.request,
                impact=None,
            )
            response = stages.call(
                run,
                ModuleResult[NarrativeDraft],
                lambda context: port.revise(revise_request, context),
                request=revise_request,
                unit=active.round_id,
            )
            if response.outcome != "blocked":
                run = updated(
                    run,
                    control=updated(
                        run.control,
                        revision_rounds=(
                            *run.control.revision_rounds[:-1],
                            updated(active, completed=True),
                        ),
                    ),
                )
        else:
            response = stages.call(
                run,
                ModuleResult[NarrativeDraft],
                lambda context: port.draft(request, context),
                request=request,
            )
        if action == "revise" and response.payload is not None:
            response = updated(
                response,
                payload=updated(
                    response.payload,
                    package=updated(
                        response.payload.package,
                        content_version="auto-" + str(run.state.narrative_revisions_started),
                    ),
                ),
            )
        run = self.append(run, "narrative-result-" + str(run.state.revision), "report", response)
        if response.payload is not None:
            self.check_draft(run, response.payload)
        if response.outcome == "research_required":
            if response.payload is not None:
                run = self.draft_artifacts(run, response.payload)
            previous = self.previous(run)
            if previous is not None and run.control.revision_request is None:
                revision = RevisionRequest(
                    request_id="facts-" + str(run.state.revision),
                    feedback=response.reason,
                    target_ids=(previous.package.game.chapter_id,),
                    reason=response.reason,
                    locked_fields=run.locked_fields,
                )
                run = updated(run, control=updated(run.control, revision_request=revision))
            stages.router.research(
                run, response.evidence_requests, "revise" if previous is not None else "draft"
            )
            return
        if response.outcome == "changes_required":
            if response.payload is not None:
                run = self.draft_artifacts(run, response.payload)
            if self.previous(run) is None:
                stages.router.stop(
                    run, "REVISION_REQUEST_INVALID", "Changes require a concrete draft to revise"
                )
            else:
                self.request_revision(run, response.reason, response.changed_ids)
            return
        if response.outcome != "completed":
            stages.completed(run, response)
            return
        assert response.payload is not None
        draft = response.payload
        run = self.draft_artifacts(run, draft)
        run = updated(
            run, review_requests=tuple(r for r in run.review_requests if r.gate == "evidence")
        )
        if any(issue.severity == "blocking" for issue in response.issues):
            self.request_revision(
                run, response.reason, response.changed_ids or (draft.package.game.chapter_id,)
            )
            return
        if run.control.professional_review:
            run = updated(
                run,
                control=updated(
                    run.control,
                    action="review",
                    review_request_id="review-" + str(run.state.revision),
                ),
            )
            next_node: NodeName = "draft_narrative"
        else:
            run = updated(run, control=updated(run.control, action="draft"))
            next_node = "narrative_review"
        stages.save_artifact(
            run,
            "draft",
            "report",
            draft,
            next_node,
            narrative_ref=self.ref(run, "narrative", "narrative", draft.package),
            runtime_ref=None,
            pending_request_id=None,
            pending_review_id=None,
            dirty_target_ids=(),
        )

    def review_result(self, run: RunRecord, response: ModuleResult[NarrativeReview]) -> None:
        stages = self.stages
        if response.payload is not None:
            if response.payload.narrative_ref != stages.reference(run, "narrative"):
                raise ServiceError(
                    "REVIEW_STALE", "Professional review refers to another narrative version"
                )
            run = self.append(
                run, "professional-review-" + str(run.state.revision), "report", response.payload
            )
        if response.outcome == "research_required":
            previous = self.previous(run)
            assert previous is not None
            revision = RevisionRequest(
                request_id="review-facts-" + str(run.state.revision),
                feedback=response.reason,
                target_ids=(previous.package.game.chapter_id,),
                reason=response.reason,
                locked_fields=run.locked_fields,
            )
            run = updated(run, control=updated(run.control, revision_request=revision))
            stages.router.research(run, response.evidence_requests, "revise")
        elif response.outcome == "changes_required":
            self.request_revision(run, response.reason, response.changed_ids)
        elif response.outcome == "completed" and response.payload is not None:
            if any(
                issue.severity == "blocking"
                for issue in (*response.issues, *response.payload.issues)
            ):
                previous = self.previous(run)
                assert previous is not None
                self.request_revision(run, response.reason, (previous.package.game.chapter_id,))
            else:
                self.stages.database.save(
                    updated(
                        run,
                        state=updated(
                            run.state,
                            revision=run.state.revision + 1,
                            node="narrative_review",
                            status="running",
                            pending_request_id=None,
                        ),
                    ),
                    run.state.revision,
                    "Professional report ready for human review",
                )
        else:
            stages.completed(run, response)

    def request_revision(self, run: RunRecord, reason: str, targets: tuple[str, ...]) -> None:
        self.stages.router.revision(
            run,
            RevisionRequest(
                request_id="revision-request-" + str(run.state.revision),
                feedback=reason,
                target_ids=targets,
                reason=reason,
                locked_fields=run.locked_fields,
            ),
        )

    def check_draft(self, run: RunRecord, draft: NarrativeDraft) -> None:
        if (
            draft.package.project_id != run.state.project_id
            or draft.package.candidate_id != run.state.selected_candidate_id
            or draft.package.evidence_package_hash != self.stages.reference(run, "evidence").sha256
            or draft.package.routes != (self.stages.reference(run, "route"),)
        ):
            raise ServiceError(
                "STORY_DEPENDENCY_CHANGED",
                "Narrative must retain current reviewed evidence, route and direction",
            )
        for field in run.locked_fields:
            if story_field_hash(draft, field.json_pointer) != field.value_sha256:
                raise ServiceError("FIELD_LOCKED", "Narrative adapter changed a locked game field")

    def previous(self, run: RunRecord) -> NarrativeDraft | None:
        return (
            self.stages.load(run, "draft", NarrativeDraft)
            if any(a.reference.artifact_id == run.state.run_id + ":draft" for a in run.artifacts)
            else None
        )

    @staticmethod
    def ref(run: RunRecord, name: str, kind: ArtifactKind, payload: Contract) -> ArtifactRef:
        return ArtifactRef(
            artifact_id=run.state.run_id + ":" + name,
            project_id=run.state.project_id,
            kind=kind,
            schema_version="0.1.0",
            content_version=payload.content_version
            if isinstance(payload, VersionedPayload)
            else payload.package.content_version
            if isinstance(payload, NarrativeDraft)
            else CanonicalSerializer.digest(payload)[:24],
            sha256=CanonicalSerializer.digest(payload),
        )

    def append(self, run: RunRecord, name: str, kind: ArtifactKind, payload: Contract) -> RunRecord:
        reference = self.ref(run, name, kind, payload)
        return updated(
            run,
            artifacts=(
                *run.artifacts,
                StoredArtifact(reference=reference, payload_json=payload.model_dump_json()),
            ),
        )

    def draft_artifacts(self, run: RunRecord, draft: NarrativeDraft) -> RunRecord:
        return self.append(
            self.append(run, "narrative", "narrative", draft.package), "draft", "report", draft
        )
