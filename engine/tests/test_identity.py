from witness_engine.ids import content_id


def test_content_id_is_stable():
    assert content_id("witness") == content_id("witness")
    assert content_id("witness") != content_id("other")
