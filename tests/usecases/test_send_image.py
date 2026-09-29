from mentor.adapters.render.fake import FakeRenderer
from mentor.adapters.telegram.fake import FakeChat
from mentor.usecases import send_image


def test_renders_and_sends_photo():
    renderer, chat = FakeRenderer(b"PNGDATA"), FakeChat()

    note = send_image.run(renderer, chat, {"diagram": "gantt\n  title t", "caption": "Plan"})

    assert note == "(image sent)"
    assert renderer.rendered == ["gantt\n  title t"]
    assert chat.photos == [(b"PNGDATA", "Plan")]


def test_render_failure_is_reported_not_raised():
    renderer, chat = FakeRenderer(error="kroki 400: bad syntax"), FakeChat()

    note = send_image.run(renderer, chat, {"diagram": "nonsense", "caption": None})

    assert "could not render" in note and "kroki 400" in note
    assert chat.photos == []


def test_missing_diagram_sends_nothing():
    assert "nothing sent" in send_image.run(FakeRenderer(), FakeChat(), {"caption": "x"})
