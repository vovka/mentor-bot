import email
import imaplib

import pytest

from mentor.adapters.mail.fake import FakeMail
from mentor.adapters.mail.imap import ImapDrafts

LOCALIZED = b'(\\HasNoChildren \\Drafts) "/" "[Gmail]/&BCcENQRABD0ENdQEMgQ6BDg-"'
OTHER = b'(\\HasNoChildren) "/" "INBOX"'


class FakeImap:
    lines: list[bytes] = []
    last: "FakeImap"

    def __init__(self, host):
        self.host, self.appended, self.logged_out = host, None, False
        FakeImap.last = self

    def login(self, user, password):
        self.creds = (user, password)

    def list(self):
        return "OK", self.lines

    def append(self, mailbox, flags, date_time, message):
        self.appended = (mailbox, flags, message)
        return "OK", [b""]

    def logout(self):
        self.logged_out = True


@pytest.fixture
def imap(monkeypatch):
    monkeypatch.setattr(imaplib, "IMAP4_SSL", FakeImap)
    return FakeImap


def test_draft_goes_to_special_use_mailbox_with_headers_and_utf8_body(imap):
    imap.lines = [OTHER, LOCALIZED]

    ImapDrafts("me@x.com", "pw").draft("to@y.com", "Привіт", "Текст листа")

    mailbox, flags, raw = imap.last.appended
    assert mailbox == '"[Gmail]/&BCcENQRABD0ENdQEMgQ6BDg-"'
    assert flags == r"\Draft"
    msg = email.message_from_bytes(raw)
    assert (msg["From"], msg["To"]) == ("me@x.com", "to@y.com")
    assert str(email.header.make_header(email.header.decode_header(msg["Subject"]))) == "Привіт"
    assert msg["Date"]
    assert msg.get_payload(decode=True).decode("utf-8").strip() == "Текст листа"
    assert imap.last.logged_out and imap.last.creds == ("me@x.com", "pw")


def test_falls_back_to_gmail_drafts_without_attribute(imap):
    imap.lines = [OTHER]

    ImapDrafts("me@x.com", "pw").draft("to@y.com", "s", "b")

    assert imap.last.appended[0] == '"[Gmail]/Drafts"'


def test_errors_propagate_and_logout_still_runs(imap, monkeypatch):
    imap.lines = []

    def boom(self, *args):
        raise imaplib.IMAP4.error("nope")

    monkeypatch.setattr(FakeImap, "append", boom)

    with pytest.raises(imaplib.IMAP4.error):
        ImapDrafts("me@x.com", "pw").draft("a", "s", "b")
    assert imap.last.logged_out


def test_fake_mail_records_drafts():
    mail = FakeMail()
    mail.draft("a", "s", "b")
    assert mail.drafts == [("a", "s", "b")]
