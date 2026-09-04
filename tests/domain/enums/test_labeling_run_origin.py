from domain.enums import LabelingRunOrigin


def test_members_carry_their_lowercase_names_as_values() -> None:
    assert LabelingRunOrigin.BATCH == "batch"
    assert LabelingRunOrigin.LIVE == "live"


def test_the_vocabulary_is_closed_to_two_members() -> None:
    assert {member.value for member in LabelingRunOrigin} == {"batch", "live"}
