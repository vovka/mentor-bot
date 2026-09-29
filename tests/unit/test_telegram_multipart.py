from mentor.adapters.telegram.api import _multipart


def test_multipart_body_has_fields_and_file():
    body, content_type = _multipart({"chat_id": "1", "caption": "c"}, "photo", "d.png", b"\x89PNG")

    boundary = content_type.split("boundary=")[1]
    assert body.count(f"--{boundary}".encode()) == 4  # 3 parts + closing
    assert b'name="chat_id"\r\n\r\n1\r\n' in body
    assert b'name="photo"; filename="d.png"\r\nContent-Type: image/png\r\n\r\n\x89PNG\r\n' in body
    assert body.endswith(f"--{boundary}--\r\n".encode())
