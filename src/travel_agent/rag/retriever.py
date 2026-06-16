import math
import re
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any


# Якорим путь к документам на корень проекта, чтобы RAG работал из любого cwd.
_PROJECT_ROOT = Path(__file__).resolve().parents[3]
DEFAULT_DOCUMENTS_DIR = _PROJECT_ROOT / "data" / "documents"


STOPWORDS = {
    "и",
    "в",
    "во",
    "на",
    "по",
    "для",
    "с",
    "со",
    "к",
    "ко",
    "от",
    "до",
    "из",
    "за",
    "при",
    "что",
    "как",
    "или",
    "если",
    "то",
    "это",
    "не",
    "но",
    "а",
    "the",
    "a",
    "an",
    "and",
    "or",
    "of",
    "to",
    "in",
    "for",
    "with",
    "is",
    "are",
}


@dataclass
class DocumentChunk:
    """
    Represents one retrievable document chunk.

    A chunk is a small part of a markdown document with source metadata.
    """

    chunk_id: str
    source_path: str
    title: str
    text: str


def tokenize(text: str) -> list[str]:
    """
    Tokenizes Russian and English text for lexical retrieval.

    @param text Source text.
    @return List of normalized tokens without common stopwords.
    """
    tokens = re.findall(r"[a-zа-яё0-9]+", text.lower(), flags=re.IGNORECASE)

    return [token for token in tokens if token not in STOPWORDS and len(token) > 1]


def extract_title(markdown_text: str, fallback_title: str) -> str:
    """
    Extracts document title from the first markdown heading.

    @param markdown_text Full markdown text.
    @param fallback_title Title used if no heading is found.
    @return Extracted or fallback title.
    """
    for line in markdown_text.splitlines():
        stripped = line.strip()

        if stripped.startswith("#"):
            return stripped.lstrip("#").strip()

    return fallback_title


def split_markdown_into_sections(markdown_text: str) -> list[str]:
    """
    Splits markdown text into sections using headings.

    @param markdown_text Full markdown text.
    @return List of markdown sections.
    """
    lines = markdown_text.splitlines()
    sections: list[list[str]] = []
    current_section: list[str] = []

    for line in lines:
        if line.strip().startswith("#") and current_section:
            sections.append(current_section)
            current_section = [line]
        else:
            current_section.append(line)

    if current_section:
        sections.append(current_section)

    return ["\n".join(section).strip() for section in sections if "\n".join(section).strip()]


def split_long_text(
    text: str,
    max_chars: int = 1200,
    overlap_chars: int = 150,
) -> list[str]:
    """
    Splits long text into overlapping chunks.

    @param text Source text.
    @param max_chars Maximum chunk size in characters.
    @param overlap_chars Number of overlapping characters between chunks.
    @return List of text chunks.
    """
    if len(text) <= max_chars:
        return [text]

    chunks = []
    start = 0

    while start < len(text):
        end = start + max_chars
        chunk = text[start:end].strip()

        if chunk:
            chunks.append(chunk)

        if end >= len(text):
            break

        start = max(0, end - overlap_chars)

    return chunks


def load_markdown_documents(
    documents_dir: Path | str = DEFAULT_DOCUMENTS_DIR,
    max_chars: int = 1200,
) -> list[DocumentChunk]:
    """
    Loads markdown policy documents and converts them into chunks.

    @param documents_dir Directory with markdown documents.
    @param max_chars Maximum chunk size.
    @return List of document chunks.
    @raises FileNotFoundError If documents directory does not exist.
    """
    documents_dir = Path(documents_dir)

    if not documents_dir.exists():
        raise FileNotFoundError(f"Documents directory not found: {documents_dir}")

    markdown_files = sorted(documents_dir.glob("*.md"))

    if not markdown_files:
        raise FileNotFoundError(f"No markdown files found in: {documents_dir}")

    chunks: list[DocumentChunk] = []

    for markdown_path in markdown_files:
        text = markdown_path.read_text(encoding="utf-8")
        document_title = extract_title(text, fallback_title=markdown_path.stem)

        sections = split_markdown_into_sections(text)

        for section_index, section in enumerate(sections):
            section_chunks = split_long_text(section, max_chars=max_chars)

            for chunk_index, chunk_text in enumerate(section_chunks):
                chunk_id = f"{markdown_path.stem}:{section_index}:{chunk_index}"

                chunks.append(
                    DocumentChunk(
                        chunk_id=chunk_id,
                        source_path=str(markdown_path.as_posix()),
                        title=document_title,
                        text=chunk_text,
                    )
                )

    return chunks


class PolicyRetriever:
    """
    Lightweight lexical retriever over markdown policy documents.

    This class implements a deterministic local retrieval layer. It does not
    require external APIs or embedding models. The retriever is suitable for
    small educational datasets and can later be replaced with a vector store
    while preserving the public retrieve/format_context interface.
    """

    def __init__(
        self,
        documents_dir: Path | str = DEFAULT_DOCUMENTS_DIR,
        max_chars: int = 1200,
    ) -> None:
        """
        Initializes retriever and loads document chunks.

        @param documents_dir Directory with markdown policy documents.
        @param max_chars Maximum chunk size.
        """
        self.documents_dir = Path(documents_dir)
        self.chunks = load_markdown_documents(
            documents_dir=self.documents_dir,
            max_chars=max_chars,
        )

        self._chunk_tokens = [tokenize(chunk.text) for chunk in self.chunks]
        self._document_frequency = self._build_document_frequency()

    def _build_document_frequency(self) -> dict[str, int]:
        """
        Builds token document frequency index.

        @return Mapping from token to number of chunks containing this token.
        """
        document_frequency: dict[str, int] = {}

        for tokens in self._chunk_tokens:
            for token in set(tokens):
                document_frequency[token] = document_frequency.get(token, 0) + 1

        return document_frequency

    def _idf(self, token: str) -> float:
        """
        Calculates inverse document frequency for token.

        @param token Query token.
        @return IDF score.
        """
        number_of_chunks = len(self.chunks)
        frequency = self._document_frequency.get(token, 0)

        return math.log((number_of_chunks + 1) / (frequency + 1)) + 1.0

    def _score_chunk(
        self,
        query: str,
        query_tokens: list[str],
        chunk: DocumentChunk,
        chunk_tokens: list[str],
    ) -> float:
        """
        Scores one chunk against a query.

        @param query Original query text.
        @param query_tokens Tokenized query.
        @param chunk Candidate chunk.
        @param chunk_tokens Tokenized chunk.
        @return Relevance score.
        """
        if not query_tokens or not chunk_tokens:
            return 0.0

        chunk_token_counts: dict[str, int] = {}

        for token in chunk_tokens:
            chunk_token_counts[token] = chunk_token_counts.get(token, 0) + 1

        score = 0.0

        for token in query_tokens:
            token_frequency = chunk_token_counts.get(token, 0)

            if token_frequency > 0:
                score += (1.0 + math.log(token_frequency)) * self._idf(token)

        query_lower = query.lower()
        chunk_lower = chunk.text.lower()

        if query_lower in chunk_lower:
            score += 5.0

        for token in set(query_tokens):
            if token in chunk.title.lower():
                score += 1.5

        return score

    def retrieve(
        self,
        query: str,
        top_k: int = 4,
        min_score: float = 0.0,
    ) -> list[dict[str, Any]]:
        """
        Retrieves most relevant policy chunks for a query.

        @param query User query or agent information need.
        @param top_k Number of chunks to return.
        @param min_score Minimum relevance score.
        @return Ranked list of chunk dictionaries.
        """
        query_tokens = tokenize(query)

        scored_chunks = []

        for chunk, chunk_tokens in zip(self.chunks, self._chunk_tokens, strict=True):
            score = self._score_chunk(
                query=query,
                query_tokens=query_tokens,
                chunk=chunk,
                chunk_tokens=chunk_tokens,
            )

            if score > min_score:
                chunk_dict = asdict(chunk)
                chunk_dict["score"] = round(score, 4)
                scored_chunks.append(chunk_dict)

        return sorted(
            scored_chunks,
            key=lambda item: item["score"],
            reverse=True,
        )[:top_k]

    def format_context(
        self,
        chunks: list[dict[str, Any]],
    ) -> str:
        """
        Formats retrieved chunks as prompt-ready context.

        @param chunks Retrieved chunk dictionaries.
        @return Context string for the agent prompt.
        """
        if not chunks:
            return "No relevant policy context found."

        formatted_chunks = []

        for index, chunk in enumerate(chunks, start=1):
            formatted_chunks.append(
                "\n".join(
                    [
                        f"[{index}] Source: {chunk['source_path']}",
                        f"Title: {chunk['title']}",
                        f"Score: {chunk['score']}",
                        "Content:",
                        chunk["text"],
                    ]
                )
            )

        return "\n\n---\n\n".join(formatted_chunks)


def retrieve_policy_context(
    query: str,
    top_k: int = 4,
    documents_dir: Path | str = DEFAULT_DOCUMENTS_DIR,
) -> dict[str, Any]:
    """
    Retrieves policy context for the agent.

    This is the main public RAG function. The agent can call it before
    answering info, planning, replanning, clarification or escalation queries.

    @param query User query or agent information need.
    @param top_k Number of chunks to retrieve.
    @param documents_dir Directory with markdown policy documents.
    @return Dictionary with raw chunks and formatted context.
    """
    retriever = PolicyRetriever(documents_dir=documents_dir)
    chunks = retriever.retrieve(query=query, top_k=top_k)

    return {
        "query": query,
        "chunks": chunks,
        "context": retriever.format_context(chunks),
    }