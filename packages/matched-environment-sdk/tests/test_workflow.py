import sqlite3
import tempfile
import unittest
from pathlib import Path

from pastport_matched_environment.workflow.graph import (
    FixedStage,
    FixedWorkflow,
    RecoveryRequired,
    RunConflict,
    StageCommand,
    StageJournal,
    StageOutput,
    StageRecovery,
)


class CounterStage:
    def __init__(self, fail: bool = False) -> None:
        self.calls = 0
        self.fail = fail

    def execute(self, command: StageCommand) -> StageOutput:
        self.calls += 1
        if self.fail:
            raise TimeoutError("Simulated uncertain dispatch")
        return StageOutput(references=("fixture:result",))


class WorkflowTests(unittest.TestCase):
    def test_replay_and_changed_binding_conflict(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            journal = StageJournal(Path(directory) / "stages.sqlite3")
            first, second = CounterStage(), CounterStage()
            workflow = FixedWorkflow(
                journal, (FixedStage("first", first), FixedStage("second", second)), "v1"
            )
            initial = workflow.run("project", "run:1", "input:1")
            self.assertEqual(workflow.run("project", "run:1", "input:1"), initial)
            self.assertEqual((first.calls, second.calls), (1, 1))
            with self.assertRaises(RunConflict):
                workflow.run("project", "run:1", "input:2")

    def test_uncertain_dispatch_stops_without_redispatch(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            stage = CounterStage(fail=True)
            workflow = FixedWorkflow(
                StageJournal(Path(directory) / "stages.sqlite3"),
                (FixedStage("model", stage),),
                "v1",
            )
            with self.assertRaises(TimeoutError):
                workflow.run("project", "run:1", "input:1")
            with self.assertRaises(RecoveryRequired):
                workflow.run("project", "run:1", "input:1")
            self.assertEqual(stage.calls, 1)


class EvidenceFailure(ValueError):
    pass


class RecoverableEvidenceStage(CounterStage):
    def execute(self, command: StageCommand) -> StageOutput:
        self.calls += 1
        if self.fail:
            raise EvidenceFailure("Known semantic rejection")
        return StageOutput(references=("fixture:accepted",), gaps=("rejected_claim:parent",))


class RecoveryTests(unittest.TestCase):
    def test_recovery_is_explicit_bound_audited_and_skips_completed_stages(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "stages.sqlite3"
            first, evidence = CounterStage(), RecoverableEvidenceStage(fail=True)
            workflow = FixedWorkflow(
                StageJournal(path),
                (FixedStage("recognize", first), FixedStage("evidence", evidence)),
                "v1",
            )
            with self.assertRaises(EvidenceFailure):
                workflow.run("project", "run:1", "input:1")
            wrong = StageRecovery("evidence", "TimeoutError", "operator review")
            with self.assertRaises(RecoveryRequired):
                workflow.run("project", "run:1", "input:1", recovery=wrong)
            recovery = StageRecovery("evidence", "EvidenceFailure", "operator review")
            with self.assertRaises(RunConflict):
                workflow.run("project", "run:1", "changed", recovery=recovery)
            evidence.fail = False
            workflow.run("project", "run:1", "input:1", recovery=recovery)
            self.assertEqual((first.calls, evidence.calls), (1, 2))
            workflow.run("project", "run:1", "input:1", recovery=recovery)
            self.assertEqual((first.calls, evidence.calls), (1, 2))
            with sqlite3.connect(path) as connection:
                audit = connection.execute(
                    "SELECT previous_status,error_type,reason FROM pipeline_recoveries"
                ).fetchall()
            self.assertEqual(audit, [("recovery_required", "EvidenceFailure", "operator review")])
