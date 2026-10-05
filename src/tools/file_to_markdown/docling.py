from io import BytesIO
from pathlib import PurePath
from threading import Lock

from docling.datamodel.base_models import (
    ConversionStatus,
    DocumentStream,
    InputFormat,
)
from docling.datamodel.pipeline_options import (
    PdfPipelineOptions,
    TableFormerMode,
)
from docling.document_converter import (
    DocumentConverter,
    PdfFormatOption,
)

from .interface import FileToMarkdown


class DoclingProvider(FileToMarkdown):
    """Convert document bytes into Markdown using Docling."""

    def __init__(
        self,
        *,
        do_ocr: bool = True,
        max_pages: int = 500,
    ) -> None:
        if not isinstance(do_ocr, bool):
            raise TypeError("do_ocr must be a boolean.")

        if type(max_pages) is not int or max_pages < 1:
            raise ValueError("max_pages must be a positive integer.")

        self._max_pages = max_pages
        self._lock = Lock()

        pdf_options = PdfPipelineOptions(
            do_ocr=do_ocr,
            do_table_structure=True,
            enable_remote_services=False,
        )

        pdf_options.table_structure_options.mode = TableFormerMode.ACCURATE

        # Create once; reuse across conversions.
        self._converter = DocumentConverter(
            allowed_formats=[
                InputFormat.PDF,
                InputFormat.CSV,
            ],
            format_options={
                InputFormat.PDF: PdfFormatOption(
                    pipeline_options=pdf_options,
                ),
            },
        )

    def _convert(self, content: bytes, *, filename: str) -> str:
        # Remove client-supplied directory paths.
        path = PurePath(filename.replace("\\", "/"))

        name = path.with_suffix(path.suffix.lower()).name

        with self._lock, BytesIO(content) as buffer:
            source = DocumentStream(name=name, stream=buffer)

            result = self._converter.convert(
                source,
                raises_on_error=True,
                max_num_pages=self._max_pages,
                max_file_size=len(content),
            )

            # Reject partial or failed conversions.
            if result.status != ConversionStatus.SUCCESS:
                raise RuntimeError(
                    f"Incomplete Docling conversion: {result.status.value}."
                )

            if result.errors:
                raise RuntimeError("Docling reported conversion errors.")

            markdown = result.document.export_to_markdown()

            return markdown
