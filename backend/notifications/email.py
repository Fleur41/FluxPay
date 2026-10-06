"""Email delivery: real SMTP, except for addresses that can never receive mail.

Test and seed accounts use reserved domains (RFC 2606: .test, .example, .invalid, .localhost and example.com/.net/.org).
Sending to them through a real mailbox only produces bounces, so those recipients are printed to the log instead.
"""

from django.core.mail.backends.console import EmailBackend as ConsoleBackend
from django.core.mail.backends.smtp import EmailBackend as SmtpBackend

RESERVED_TLDS = (".test", ".example", ".invalid", ".localhost")
RESERVED_DOMAINS = ("example.com", "example.net", "example.org")


def deliverable(address: str) -> bool:
    domain = address.rsplit("@", 1)[-1].strip(" >").lower()
    return not (domain.endswith(RESERVED_TLDS) or domain in RESERVED_DOMAINS or domain.endswith(
        tuple("." + d for d in RESERVED_DOMAINS)))  # fmt: skip


class SmtpExceptTestAddressesBackend(SmtpBackend):
    def send_messages(self, email_messages):
        real, logged = [], []
        for message in email_messages:
            recipients = message.recipients()
            if recipients and all(deliverable(r) for r in recipients):
                real.append(message)
            elif any(deliverable(r) for r in recipients):
                # Mixed: send to the real addresses only.
                message.to = [r for r in message.to if deliverable(r)]
                message.cc = [r for r in message.cc if deliverable(r)]
                message.bcc = [r for r in message.bcc if deliverable(r)]
                real.append(message)
            else:
                logged.append(message)
        if logged:
            ConsoleBackend(fail_silently=self.fail_silently).send_messages(logged)
        return (super().send_messages(real) if real else 0) + len(logged)
