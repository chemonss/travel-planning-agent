import sys
from pprint import pp

from travel_agent.rag.retriever import retrieve_policy_context


def main() -> None:
    """
    Runs manual RAG retrieval for a query from command line.
    """
    if len(sys.argv) < 2:
        query = "Что считается ночным прилётом?"
    else:
        query = " ".join(sys.argv[1:])

    result = retrieve_policy_context(
        query=query,
        top_k=4,
    )

    print("\n=== Query ===")
    print(result["query"])

    print("\n=== Retrieved chunks ===")
    for chunk in result["chunks"]:
        pp(
            {
                "chunk_id": chunk["chunk_id"],
                "source_path": chunk["source_path"],
                "title": chunk["title"],
                "score": chunk["score"],
                "preview": chunk["text"][:300],
            }
        )

    print("\n=== Formatted context ===")
    print(result["context"])


if __name__ == "__main__":
    main()