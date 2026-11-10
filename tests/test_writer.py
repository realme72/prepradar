from prepradar.report.writer import ChecklistItem, PrepGuide, Section, _enforce_citations


def test_citations_to_unknown_ids_are_removed_and_counted():
    guide = PrepGuide(
        process_overview="Two rounds [S1], then HR [S9].",            # S9 doesn't exist
        sections=[Section(category="DSA", summary="Strings [Q1] [Q7].",  # Q7 doesn't exist
                          must_prepare=["Q1", "Q2", "Q99"])],             # Q99 doesn't exist
        checklist=[ChecklistItem(item="Practise strings", question_ids=["Q1", "Q42"])],
        caveats=[],
    )
    dropped = _enforce_citations(guide, qids={"Q1", "Q2"}, sids={"S1"})
    assert dropped == 4
    assert guide.sections[0].must_prepare == ["Q1", "Q2"]
    assert guide.checklist[0].question_ids == ["Q1"]
