from commons.observability import NullProgressReporter


def test_every_method_is_a_noop() -> None:
    reporter = NullProgressReporter()

    assert reporter.begin_run(total_flows=3) is None
    assert reporter.begin_flow("knowledge_cleaning") is None
    assert reporter.begin_step("clean_articles", index=1, total=4) is None
    assert reporter.begin_items("batches", total=3) is None
    # advance_item / end_items called with no track ever opened must not raise.
    assert reporter.advance_item() is None
    assert reporter.end_items() is None
    assert reporter.end_step() is None
    assert reporter.end_flow() is None
