from request_ai_agent_i0_0.ui import HTML_TEMPLATE


def test_full_preview_uses_section_titles_without_repeated_table_captions():
    preview = HTML_TEMPLATE.split("function renderDocumentPreviewPanel", 1)[1].split(
        "function renderCandidateNotice", 1
    )[0]

    assert 'section("conditions", "해석 조건"' in preview
    assert '<thead><tr><th>조건</th><th>입력값</th></tr></thead>' in preview
    assert "<caption>해석 대상 제품</caption>" not in preview
    assert "<caption>조건 카드 목록</caption>" not in preview
    assert "<caption>Case Matrix</caption>" not in preview
    assert "조건 카드" not in preview
