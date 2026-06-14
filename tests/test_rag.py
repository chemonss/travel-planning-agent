from travel_agent.rag.retriever import (
    PolicyRetriever,
    retrieve_policy_context,
    tokenize,
)


def test_tokenize() -> None:
    """
    Checks basic tokenization for Russian and English text.
    """
    tokens = tokenize("Что считается ночным прилётом после 23:00?")

    assert "ночным" in tokens
    assert "прилётом" in tokens
    assert "23" in tokens
    assert "00" in tokens


def test_policy_retriever_loads_documents() -> None:
    """
    Checks that policy retriever loads markdown documents.
    """
    retriever = PolicyRetriever()

    assert len(retriever.chunks) > 0


def test_retrieve_policy_context_returns_chunks() -> None:
    """
    Checks that policy context retrieval returns at least one chunk.
    """
    result = retrieve_policy_context(
        query="Что считается ночным прилётом?",
        top_k=3,
    )

    assert result["query"] == "Что считается ночным прилётом?"
    assert "chunks" in result
    assert "context" in result
    assert len(result["chunks"]) > 0
    assert result["context"] != "No relevant policy context found."


def test_retrieve_hotel_cancellation_context() -> None:
    """
    Checks retrieval for hotel cancellation policy.
    """
    result = retrieve_policy_context(
        query="Можно ли бесплатно отменить отель?",
        top_k=3,
    )

    context = result["context"].lower()

    assert "отел" in context or "hotel" in context