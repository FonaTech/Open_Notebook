from open_notebook.core.llm_config import complete_chat_endpoint, parse_llm_config_profiles


def test_parse_profiles_list_default():
    parsed = parse_llm_config_profiles(
        {
            "profiles": [
                {
                    "id": "sn",
                    "provider": "openai",
                    "label": "SN",
                    "model": "sensenova-6.7-flash-lite",
                    "base_url": "https://token.sensenova.cn/v1",
                    "api_key": "sk-test",
                    "default": True,
                }
            ]
        }
    )
    assert parsed["default_profile_id"] == "sn"
    profile = parsed["profiles"][0]
    assert profile.provider == "openai_compat"
    assert profile.endpoint == "https://token.sensenova.cn/v1/chat/completions"


def test_parse_flat_kimi():
    parsed = parse_llm_config_profiles(
        {
            "provider": "kimi",
            "kimi_key": "x",
            "kimi_model": "moonshot-v1-8k",
        }
    )
    assert parsed["default_profile_id"] == "kimi"
    profile = parsed["profiles"][0]
    assert profile.provider == "kimi"
    assert profile.model == "moonshot-v1-8k"


def test_complete_endpoint():
    assert complete_chat_endpoint("https://example.test/v1") == "https://example.test/v1/chat/completions"
    assert (
        complete_chat_endpoint("https://example.test/v1/chat/completions")
        == "https://example.test/v1/chat/completions"
    )
