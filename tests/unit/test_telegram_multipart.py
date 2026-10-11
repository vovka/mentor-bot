from mentor.adapters.telegram.api import _multipart


def test_multipart_body_has_fields_and_file():
    body, content_type = _multipart({"chat_id": "1", "caption": "c"}, "photo", "d.png", b"\x89PNG")

    boundary = content_type.split("boundary=")[1]
    assert body.count(f"--{boundary}".encode()) == 4  # 3 parts + closing
    assert b'name="chat_id"\r\n\r\n1\r\n' in body
    assert b'name="photo"; filename="d.png"\r\nContent-Type: image/png\r\n\r\n\x89PNG\r\n' in body
    assert body.endswith(f"--{boundary}--\r\n".encode())


def test_multipart_content_type_is_configurable():
    body, _ = _multipart({}, "document", "n.pdf", b"x", "application/pdf")
    assert b'filename="n.pdf"\r\nContent-Type: application/pdf\r\n' in body


def test_reply_parameters_only_on_the_first_chunk():
    from mentor.adapters.telegram.api import TelegramChat

    chat, calls = TelegramChat("t", "1"), []
    chat._call = lambda method, params, timeout: calls.append(params) or {"result": {"message_id": 9}}
    chat.send("a" * 5000, reply_to=7)
    chat.send_html("<b>x</b>")
    assert calls[0]["reply_parameters"] == {"message_id": 7, "allow_sending_without_reply": True}
    assert "reply_parameters" not in calls[1] and "reply_parameters" not in calls[2]
