"""SDK port checks use an explicit transport double, not live subscription calls."""

import json
import tempfile
import unittest
from pathlib import Path

from pastport_pdf_vr.adapters.execution import SubscriptionExecutor
from pastport_pdf_vr.adapters.structured_output import StrictOutputSchema
from pastport_pdf_vr.domain.environment import LocationBatch, MatchedBatch
from pastport_pdf_vr.domain.execution import (
    ExecutionDenied,
    ExecutionInput,
    ExecutionOutput,
    ExecutionRecoveryRequired,
    ModelExecutionError,
    SDKReadiness,
    SubscriptionGrant,
)


class ExplicitTransport:
    def __init__(self) -> None:
        self.calls: list[ExecutionInput] = []
        self.fail = False
        self.tokens = 30

    def readiness(self, model_id: str) -> SDKReadiness:
        return SDKReadiness(
            authenticated=True,
            auth_mode="chatgpt",
            requested_model=model_id,
            model_available=True,
            image_input_supported=True,
        )

    def execute(self, request: ExecutionInput, timeout_seconds: int) -> ExecutionOutput:
        self.calls.append(request)
        if self.fail:
            raise ModelExecutionError("Explicit uncertain-dispatch fixture")
        return ExecutionOutput(
            payload_json='{"entities":[],"sightings":[]}',
            receipt_ref="fixture:transport",
            thread_ref="fixture:thread",
            turn_ref="fixture:turn",
            input_tokens=20,
            output_tokens=10,
            total_tokens=self.tokens,
        )


class CodexExecutionTests(unittest.TestCase):
    @staticmethod
    def request(grant: SubscriptionGrant) -> ExecutionInput:
        return ExecutionInput(
            project_id=grant.project_id,
            grant_ref=grant.grant_ref,
            model_id=grant.model_id,
            kind="environment_generation",
            prompt_version="v1",
            policy_version="v1",
            instructions="Fixture",
            payload_json="{}",
            output_schema_json="{}",
        )

    def test_receipts_cache_cap_and_immutable_grant(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "execution.sqlite3"
            grant = SubscriptionGrant(project_id="test", grant_ref="grant:1", max_calls=1)
            transport = ExplicitTransport()
            executor = SubscriptionExecutor(path, grant, transport)
            request = self.request(grant)
            result = executor.execute(request)
            self.assertTrue(result.receipt_ref.startswith("codex:"))
            self.assertEqual(SubscriptionExecutor(path, grant, transport).execute(request), result)
            self.assertEqual(len(transport.calls), 1)
            with self.assertRaises(ExecutionDenied):
                executor.execute(request.model_copy(update={"policy_version": "v2"}))
            with self.assertRaises(ExecutionDenied):
                SubscriptionExecutor(path, grant.model_copy(update={"max_calls": 2}), transport)
            with self.assertRaises(ExecutionDenied):
                executor.execute(request.model_copy(update={"project_id": "other"}))

    def test_uncertain_dispatch_blocks_new_work_and_resume(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            grant = SubscriptionGrant(project_id="test", grant_ref="grant:1")
            transport = ExplicitTransport()
            transport.fail = True
            path = Path(directory) / "execution.sqlite3"
            executor = SubscriptionExecutor(path, grant, transport)
            request = self.request(grant)
            with self.assertRaises(ModelExecutionError):
                executor.execute(request)
            transport.fail = False
            restarted = SubscriptionExecutor(path, grant, transport)
            for candidate in (request, request.model_copy(update={"policy_version": "v2"})):
                with self.assertRaises(ExecutionRecoveryRequired):
                    restarted.execute(candidate)
            self.assertEqual(len(transport.calls), 1)

    def test_recorded_token_threshold_blocks_next_call(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            grant = SubscriptionGrant(
                project_id="test", grant_ref="grant:1", max_calls=3, max_recorded_tokens=10
            )
            transport = ExplicitTransport()
            executor = SubscriptionExecutor(Path(directory) / "execution.sqlite3", grant, transport)
            request = self.request(grant)
            executor.execute(request)
            with self.assertRaises(ExecutionDenied):
                executor.execute(request.model_copy(update={"policy_version": "v2"}))
            self.assertEqual(len(transport.calls), 1)

    def test_strict_schema_requires_defaulted_and_nested_fields(self) -> None:
        for model in (LocationBatch, MatchedBatch):
            schema = json.loads(StrictOutputSchema.convert(json.dumps(model.model_json_schema())))
            self.assertEqual(set(schema["required"]), set(schema["properties"]))
            self.assertFalse(schema["additionalProperties"])
            for child in schema.get("$defs", {}).values():
                if "properties" in child:
                    self.assertEqual(set(child["required"]), set(child["properties"]))
                    self.assertFalse(child["additionalProperties"])
                    self.assertTrue(
                        all("default" not in row for row in child["properties"].values())
                    )

