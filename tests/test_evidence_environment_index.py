"""A generated mapping exposes only supported numbered evidence to environment import."""
from pathlib import Path
import shutil

import pytest
from PIL import Image

from pastport_evidence.adapters.document_export import PDFRenderer
from pastport_evidence.domain.report import ImageFrame, ReportDocument, ReportPage, TextFrame
from pastport_matched_environment.adapters.assets import LocalAssetStore
from pastport_matched_environment.adapters.matched_pdf import MatchedPDFIndexReader
from pastport_matched_environment.adapters.pdf import PopplerPDFReader
from pastport_matched_environment.application.pdf_ingestion import PDFIngestionService
from pastport_matched_environment.application.environment_agent import offline_input_limits


def test_linked_mapping_excludes_unassigned_objects_without_model_calls(tmp_path: Path) -> None:
    executable=shutil.which('pdftoppm')
    if executable is None:
        pytest.skip('Poppler is required for PDF boundary integration')
    photo=tmp_path/'photo.jpg'
    Image.new('RGB',(80,60),'green').save(photo)
    document=ReportDocument(pages=(
        ReportPage((TextFrame('7 -> historical:classroom',32,24,778,24),),
            (ImageFrame(photo,32,75,300,190,'Modern desk','evidence-7'),), 'evidence-7'),
        ReportPage((TextFrame('8 - No historical assignment',32,24,778,24),),
            (ImageFrame(photo,32,75,300,190,'Unassigned'),)),
    ))
    pdf=tmp_path/'mapping.pdf'
    PDFRenderer().write(pdf,document)
    registered=PDFIngestionService(LocalAssetStore(tmp_path/'assets'),PopplerPDFReader(Path(executable))).register_and_extract('fixture',pdf,offline_input_limits())
    index=MatchedPDFIndexReader().read(pdf,registered)
    assert [(e.number,e.history_key,e.detail_page) for e in index.entries]==[(7,'historical:classroom',1)]
    assert len(index.entries[0].modern_images)==1
    assert index.entries[0].modern_images[0].page==1
