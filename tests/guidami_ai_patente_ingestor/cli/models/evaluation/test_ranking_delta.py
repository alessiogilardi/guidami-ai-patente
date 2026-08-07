from guidami_ai_patente_ingestor.cli.models.evaluation import RankingDelta


def test_construct() -> None:
    delta = RankingDelta(hit_full_delta_points={5: 3.2})

    assert delta.hit_full_delta_points == {5: 3.2}
