from __future__ import annotations

import unittest
from importlib.resources import files

from pastport_evidence.sdk import (
    OutputPaths,
    PDFDocumentReader,
    PhotoMappingWorkflow,
    SemanticTransport,
    SubscriptionGrant,
)


class EvidenceSdkBoundaryTests(unittest.TestCase):
    def test_public_workflow_contract_is_importable_without_execution(self) -> None:
        self.assertTrue(callable(PhotoMappingWorkflow))
        self.assertTrue(callable(SubscriptionGrant))
        self.assertTrue(callable(OutputPaths))
        self.assertIsNotNone(PDFDocumentReader)
        self.assertIsNotNone(SemanticTransport)

    def test_typing_marker_and_rendering_resources_are_packaged(self) -> None:
        package = files("pastport_evidence")
        self.assertTrue(package.joinpath("py.typed").is_file())
        self.assertTrue(package.joinpath("fonts/NotoSansSC-Regular.ttf").is_file())
        self.assertTrue(package.joinpath("prompts/pdf_matching_v2.txt").is_file())


if __name__ == "__main__":
    unittest.main()
