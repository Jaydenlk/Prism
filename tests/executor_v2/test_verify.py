import pytest


def test_should_verify_simple_chat():
    from executor_v2.userbrain.verify import should_verify

    assert should_verify("hello") is False
    assert should_verify("hi") is False
    # U+8C22 U+8C22 = xie xie (thank you)
    assert should_verify("谢谢") is False


def test_should_verify_research():
    from executor_v2.userbrain.verify import should_verify

    # U+5E2E U+6211 U+8C03 U+7814 U+4E00 U+4E0B AI U+6846 U+67B6 = help me research AI frameworks
    assert should_verify("帮我调研一下AI框架") is True
    assert should_verify("research the latest trends") is True
    # U+5206 U+6790 U+8FD9 U+4E2A U+9879 U+76EE U+7684 U+8BE6 U+7EC6 U+6570 U+636E = analyze this project detailed data
    assert should_verify("分析这个项目的详细数据") is True


def test_should_verify_short_text():
    from executor_v2.userbrain.verify import should_verify

    assert should_verify("ok") is False
    assert should_verify("abc") is False


def test_intent_categories_complete():
    from executor_v2.userbrain.router import INTENT_CATEGORIES

    assert len(INTENT_CATEGORIES) == 8
    assert "chat" in INTENT_CATEGORIES
    assert "research" in INTENT_CATEGORIES
    assert "memo" in INTENT_CATEGORIES
