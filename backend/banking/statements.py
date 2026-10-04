"""Account statements: one builder, rendered as CSV or PDF so both always show the same numbers."""
import csv
import io
from dataclasses import dataclass, field
from datetime import date, datetime, time, timedelta
from decimal import Decimal
from zoneinfo import ZoneInfo

from django.conf import settings
from django.utils import timezone

from .models import Account, Transaction
from .services import holder_name

@dataclass
class Statement:
    account: Account
    holder: str
    start: date
    end: date  # inclusive
    opening_balance: Decimal
    closing_balance: Decimal
    money_in: Decimal = Decimal("0.00")
    money_out: Decimal = Decimal("0.00")
    lines: list = field(default_factory=list)
    generated_at: datetime = field(default_factory=timezone.now)

    @property
    def filename_stem(self) -> str:
        return f"FluxPay-statement-{self.account.account_number}-{self.start}-to-{self.end}"


def build_statement(account: Account, start: date, end: date) -> Statement:
    """Every ledger line from `start` to `end` (whole days in FLUXPAY_DISPLAY_TIMEZONE), oldest first.

    Failed lines are kept: a failed payout's hold and its reversal both changed the balance column.
    """
    zone = ZoneInfo(settings.FLUXPAY_DISPLAY_TIMEZONE)
    since = datetime.combine(start, time.min, tzinfo=zone)
    until = datetime.combine(end + timedelta(days=1), time.min, tzinfo=zone)

    before = Transaction.objects.filter(account=account, created_at__lt=since).order_by("-created_at", "-id").first()
    opening = before.balance_after if before else Decimal("0.00")
    lines = list(
        Transaction.objects.filter(account=account, created_at__gte=since, created_at__lt=until).order_by(
            "created_at", "id"
        )
    )
    statement = Statement(
        account=account,
        holder=holder_name(account),
        start=start,
        end=end,
        opening_balance=opening,
        closing_balance=lines[-1].balance_after if lines else opening,
        lines=lines,
    )
    for line in lines:
        if line.type == Transaction.Type.CREDIT:
            statement.money_in += line.amount
        else:
            statement.money_out += line.amount
    return statement


def _local(moment) -> datetime:
    return timezone.localtime(moment, ZoneInfo(settings.FLUXPAY_DISPLAY_TIMEZONE))


def _counterparty(line: Transaction) -> str:
    if line.counterparty_account:
        return f"{line.counterparty_name} (••{line.counterparty_account[-4:]})"
    return line.counterparty_name


def render_csv(statement: Statement) -> bytes:
    out = io.StringIO()
    writer = csv.writer(out)
    currency = statement.account.currency
    writer.writerow(["FluxPay account statement"])
    writer.writerow(["Account holder", statement.holder])
    writer.writerow(["Account number", statement.account.account_number])
    writer.writerow(["Period", statement.start.isoformat(), statement.end.isoformat()])
    writer.writerow(["Currency", currency])
    writer.writerow(["Opening balance", f"{statement.opening_balance:.2f}"])
    writer.writerow(["Money in", f"{statement.money_in:.2f}"])
    writer.writerow(["Money out", f"{statement.money_out:.2f}"])
    writer.writerow(["Closing balance", f"{statement.closing_balance:.2f}"])
    writer.writerow([])
    writer.writerow(["Date", "Reference", "Description", "Counterparty", "Status", "Money in", "Money out", "Balance"])
    for line in statement.lines:
        credit = line.type == Transaction.Type.CREDIT
        writer.writerow(
            [
                _local(line.created_at).strftime("%Y-%m-%d %H:%M"),
                line.reference,
                line.description,
                _counterparty(line),
                line.get_status_display(),
                f"{line.amount:.2f}" if credit else "",
                "" if credit else f"{line.amount:.2f}",
                f"{line.balance_after:.2f}",
            ]
        )
    # UTF-8 with BOM so Excel shows names with accents correctly.
    return ("﻿" + out.getvalue()).encode("utf-8")


def render_pdf(statement: Statement) -> bytes:
    from reportlab.lib import colors
    from reportlab.lib.pagesizes import A4
    from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
    from reportlab.lib.units import mm
    from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle

    currency = statement.account.currency
    styles = getSampleStyleSheet()
    small = ParagraphStyle("small", parent=styles["BodyText"], fontSize=8, leading=10)
    muted = ParagraphStyle("muted", parent=small, textColor=colors.HexColor("#6B6880"))
    brand = colors.HexColor("#4F3BD8")

    def money(value: Decimal) -> str:
        return f"{value:,.2f}"

    story = [
        Paragraph("<b>FluxPay</b> account statement", ParagraphStyle("title", parent=styles["Title"], textColor=brand,
                                                                     alignment=0, fontSize=18)),
        Spacer(1, 4 * mm),
        Table(
            [
                ["Account holder", statement.holder, "Period", f"{statement.start:%d %b %Y} – {statement.end:%d %b %Y}"],
                ["Account number", statement.account.account_number, "Currency", currency],
            ],
            colWidths=[30 * mm, 60 * mm, 22 * mm, 68 * mm],
            style=TableStyle([
                ("FONTSIZE", (0, 0), (-1, -1), 9),
                ("TEXTCOLOR", (0, 0), (0, -1), colors.HexColor("#6B6880")),
                ("TEXTCOLOR", (2, 0), (2, -1), colors.HexColor("#6B6880")),
                ("LEFTPADDING", (0, 0), (-1, -1), 0),
            ]),
        ),
        Spacer(1, 5 * mm),
        Table(
            [
                ["Opening balance", "Money in", "Money out", "Closing balance"],
                [money(statement.opening_balance), money(statement.money_in), money(statement.money_out),
                 money(statement.closing_balance)],
            ],
            colWidths=[45 * mm] * 4,
            style=TableStyle([
                ("FONTSIZE", (0, 0), (-1, 0), 8),
                ("TEXTCOLOR", (0, 0), (-1, 0), colors.HexColor("#6B6880")),
                ("FONTSIZE", (0, 1), (-1, 1), 12),
                ("FONTNAME", (0, 1), (-1, 1), "Helvetica-Bold"),
                ("BOX", (0, 0), (-1, -1), 0.5, colors.HexColor("#D9D6E8")),
                ("TOPPADDING", (0, 0), (-1, -1), 6),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 6),
            ]),
        ),
        Spacer(1, 6 * mm),
    ]

    header = ["Date", "Description", "Reference", f"In ({currency})", f"Out ({currency})", f"Balance ({currency})"]
    rows = [header]
    for line in statement.lines:
        credit = line.type == Transaction.Type.CREDIT
        description = line.description or line.get_category_display()
        detail = _counterparty(line)
        if line.status != Transaction.Status.COMPLETED:
            detail = f"{detail} · {line.get_status_display()}" if detail else line.get_status_display()
        rows.append([
            Paragraph(_local(line.created_at).strftime("%d %b %Y<br/>%H:%M"), small),
            Paragraph(f"{_escape(description)}<br/><font color='#6B6880'>{_escape(detail)}</font>", small),
            Paragraph(line.reference, muted),
            money(line.amount) if credit else "",
            "" if credit else money(line.amount),
            money(line.balance_after),
        ])
    if len(rows) == 1:
        rows.append([Paragraph("No transactions in this period.", small), "", "", "", "", ""])

    table = Table(rows, colWidths=[22 * mm, 62 * mm, 30 * mm, 22 * mm, 22 * mm, 24 * mm], repeatRows=1)
    table.setStyle(TableStyle([
        ("FONTSIZE", (0, 0), (-1, -1), 8),
        ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
        ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#EEEBFB")),
        ("ALIGN", (3, 0), (-1, -1), "RIGHT"),
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("LINEBELOW", (0, 1), (-1, -1), 0.25, colors.HexColor("#E4E1EE")),
        ("TEXTCOLOR", (3, 1), (3, -1), colors.HexColor("#0E7A50")),
    ]))
    story.append(table)

    generated = _local(statement.generated_at).strftime("%d %b %Y %H:%M")

    def footer(canvas, doc):
        canvas.saveState()
        canvas.setFont("Helvetica", 7)
        canvas.setFillColor(colors.HexColor("#6B6880"))
        canvas.drawString(15 * mm, 10 * mm, f"Generated {generated} ({settings.FLUXPAY_DISPLAY_TIMEZONE}) · FluxPay")
        canvas.drawRightString(A4[0] - 15 * mm, 10 * mm, f"Page {doc.page}")
        canvas.restoreState()

    buffer = io.BytesIO()
    doc = SimpleDocTemplate(
        buffer, pagesize=A4, leftMargin=15 * mm, rightMargin=15 * mm, topMargin=15 * mm, bottomMargin=18 * mm,
        title=statement.filename_stem, author="FluxPay",
    )
    doc.build(story, onFirstPage=footer, onLaterPages=footer)
    return buffer.getvalue()


def _escape(text: str) -> str:
    return (text or "").replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
