from app.jobs import llm_prompts


def test_attached_image_sentinel_matches_documented_literal_value():
    # Must byte-for-byte match host/llm_bridge/config.py's own copy of this
    # literal string -- no shared import between the two by design (see
    # llm_prompts.py's comment). Asserted literally on both sides so a
    # one-sided edit fails its own suite instead of only failing against the
    # real other side.
    assert llm_prompts.ATTACHED_IMAGE_SENTINEL == "<<ATTACHED_IMAGE>>"


def test_vision_prompts_contain_the_sentinel():
    assert llm_prompts.ATTACHED_IMAGE_SENTINEL in llm_prompts.FLOOR_AREA_VISION_PROMPT
    assert llm_prompts.ATTACHED_IMAGE_SENTINEL in llm_prompts.EPC_VISION_PROMPT
