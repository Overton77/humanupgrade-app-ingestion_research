from __future__ import annotations

from typing import Iterable

from pydantic import BaseModel


class Document(BaseModel):
    id: str
    text: str


def summarize_docs(docs: Iterable[Document], max_length: int = 200) -> str:
    """Return a simple truncated summary of all document texts."""
    combined = " ".join(doc.text for doc in docs)
    if len(combined) <= max_length:
        return combined
    return combined[: max_length - 3] + "..."


if __name__ == "__main__":
    docs = [
        Document(id="1", text="Hello world."),
        Document(id="2", text="This is a small test document."),
    ]
    print(summarize_docs(docs, max_length=50))
