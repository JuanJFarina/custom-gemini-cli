from harle_api.telegram import extract_text_message


def test_extract_text_message_includes_valid_update_id() -> None:
    message = extract_text_message(
        {
            "update_id": 123,
            "message": {
                "text": " Hello ",
                "chat": {"id": 456},
                "from": {
                    "id": 789,
                    "first_name": "Beta",
                    "last_name": "User",
                },
            },
        },
    )

    assert message is not None
    assert message.update_id == 123
    assert message.chat_id == 456
    assert message.user_id == 789
    assert message.user_name == "Beta User"
    assert message.text == "Hello"


def test_extract_text_message_rejects_invalid_update_id() -> None:
    for update_id in (None, True, -1, "123"):
        assert (
            extract_text_message(
                {
                    "update_id": update_id,
                    "message": {
                        "text": "Hello",
                        "chat": {"id": 456},
                        "from": {"id": 789},
                    },
                },
            )
            is None
        )
