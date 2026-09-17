from test_retrieval import result

from traceable_rag.generation import NO_EVIDENCE, build_context, map_citations


def test_citation_mapping() -> None:
    evidence = result("a", "北京住宿标准600元")
    evidence.chunk.metadata["file_name"] = "制度.docx"
    evidence.chunk.source_location.paragraph_index = 3
    answer = map_citations("标准600元。[C1][C1]", [evidence])
    assert len(answer.citations) == 1
    assert answer.citations[0].file_name == "制度.docx"
    assert answer.citations[0].source_location.paragraph_index == 3
    assert "[C1]" in build_context([evidence])


def test_invalid_citation_refuses() -> None:
    for text in ["600元", "600元[C2]", "600元[C1][C99]", "600元[C0]", "600元[C01]"]:
        assert map_citations(text, [result("a")]).answer == NO_EVIDENCE
