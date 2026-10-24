import tempfile
import unittest
from pathlib import Path

from pastport_pdf_vr.workflow.graph import (
    FixedStage,
    FixedWorkflow,
    RecoveryRequired,
    RunConflict,
    StageCommand,
    StageJournal,
    StageOutput,
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
