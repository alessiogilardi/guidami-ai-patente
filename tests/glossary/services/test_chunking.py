from glossary.services._chunking import split_into_chunks


def test_text_under_the_limit_is_a_single_chunk() -> None:
    text = "1) ALFA: uno. 2) BETA: due."
    chunks = split_into_chunks(text, max_chars=1000)
    assert chunks == [(0, text)]


def test_a_numeric_marker_block_splits_between_entries_not_mid_entry() -> None:
    text = "1) ALFA: uno due tre. 2) BETA: quattro cinque sei. 3) GAMMA: sette otto nove."
    chunks = split_into_chunks(text, max_chars=40)
    assert len(chunks) > 1
    for _, chunk in chunks:
        assert not chunk.strip().startswith((")", ":"))
    reassembled = "".join(chunk for _, chunk in chunks)
    assert reassembled.replace(" ", "") == text.replace(" ", "")


def test_an_alphabetic_marker_block_splits_at_letter_boundaries() -> None:
    text = "a) primo termine: definizione uno; b) secondo termine: definizione due; c) terzo: tre;"
    chunks = split_into_chunks(text, max_chars=45)
    assert len(chunks) > 1
    assert chunks[0][1].strip().startswith("a)")


def test_chunk_offsets_point_back_into_the_original_text() -> None:
    text = "1) ALFA: uno. 2) BETA: due. 3) GAMMA: tre."
    chunks = split_into_chunks(text, max_chars=20)
    for start, chunk in chunks:
        assert text[start : start + len(chunk)] == chunk


def test_no_detectable_marker_falls_back_to_a_raw_character_split() -> None:
    text = "x" * 100
    chunks = split_into_chunks(text, max_chars=30)
    assert len(chunks) == 4
    assert chunks[0] == (0, "x" * 30)
