"""ImapDrafts: save an email draft over IMAP (Gmail by default). The human opens it and presses Send."""

import imaplib
import re
import time
from email.message import EmailMessage
from email.utils import formatdate

_FALLBACK = '"[Gmail]/Drafts"'
# LIST line: (\Attr \Attr) "delim" name   -- name is a quoted string or an atom
_LIST_LINE = re.compile(rb'\((?P<attrs>[^)]*)\) \S+ (?P<name>.+)$')


class ImapDrafts:
    def __init__(self, user: str, password: str, host: str = "imap.gmail.com"):
        self._user, self._password, self._host = user, password, host

    def draft(self, to: str, subject: str, body: str) -> None:
        msg = EmailMessage()
        msg["From"], msg["To"], msg["Subject"], msg["Date"] = self._user, to, subject, formatdate(localtime=True)
        msg.set_content(body, charset="utf-8")
        imap = imaplib.IMAP4_SSL(self._host)
        try:
            imap.login(self._user, self._password)
            imap.append(_drafts_mailbox(imap), r"\Draft", time.time(), msg.as_bytes())
        finally:
            imap.logout()


def _drafts_mailbox(imap) -> str:
    """Mailbox with the \\Drafts special-use attribute, exactly as the server named it (quoted)."""
    _, lines = imap.list()
    for line in lines:
        m = _LIST_LINE.match(line) if isinstance(line, bytes) else None
        if m and rb"\drafts" in m["attrs"].lower().split():
            name = m["name"].decode("ascii").strip()
            return name if name.startswith('"') else f'"{name}"'
    return _FALLBACK
