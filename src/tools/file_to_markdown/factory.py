from .interface import FileToMarkdown


def file_to_markdown_factory(provider: str = "docling") -> FileToMarkdown:
    """Return the selected implementation as a FileToMarkdown interface."""

    if not isinstance(provider, str):
        raise TypeError("provider must be a string.")

    if provider.strip().lower() == "docling":
        from .docling import DoclingProvider

        return DoclingProvider()

    raise ValueError(f"Unsupported file-to-Markdown provider: {provider}")
