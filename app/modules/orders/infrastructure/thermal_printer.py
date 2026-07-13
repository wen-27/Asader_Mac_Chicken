"""Raw ESC/POS receipt printing for thermal printers managed by CUPS."""

from __future__ import annotations

import asyncio
import subprocess
import unicodedata
from datetime import datetime
from zoneinfo import ZoneInfo

from app.modules.orders.infrastructure.models import OrderORM


RECEIPT_WIDTH = 40
BUSINESS_HEADER = [
    "ANA LUCIA PATINO RUEDA",
    "28.378.931-7",
    "MAX CHICKEN EXPRESS",
    "TELEFONO: 6488932 - 6497732",
    "CARRERA 3 # 48-06 LAGOS 2",
]


class ThermalPrinterError(RuntimeError):
    """Raised when the operating system cannot send a raw ticket to CUPS."""


async def print_order_receipt(order: OrderORM, printer_name: str) -> None:
    ticket = _build_escpos_ticket(order)
    await asyncio.to_thread(_send_to_cups, printer_name, ticket)


def _send_to_cups(printer_name: str, ticket: bytes) -> None:
    subprocess.run(["cupsaccept", printer_name], capture_output=True, check=False, timeout=5)
    subprocess.run(["cupsenable", printer_name], capture_output=True, check=False, timeout=5)
    result = subprocess.run(
        ["lp", "-d", printer_name, "-o", "raw", "-"],
        input=ticket,
        capture_output=True,
        check=False,
        timeout=20,
    )
    if result.returncode != 0:
        message = (result.stderr or result.stdout).decode("utf-8", errors="replace").strip()
        raise ThermalPrinterError(message or f"lp failed with exit code {result.returncode}")


def _build_escpos_ticket(order: OrderORM) -> bytes:
    receipt = _build_receipt_text(order)
    parts = [
        b"\x1b@",  # initialize
        b"\x1bt\x00",  # common ESC/POS code page
        b"\x1b!\x00",  # normal font
        _ascii(receipt),
        b"\n\n\n",
        b"\x1dV\x00",  # full cut on compatible printers
        b"\x1b@",
        _ascii(receipt),
        b"\n\n\n",
        b"\x1dV\x00",
    ]
    return b"".join(parts)


def _build_receipt_text(order: OrderORM) -> str:
    created_at = _local_datetime(order.created_at)
    lines: list[str] = []

    lines.extend(_center(line) for line in BUSINESS_HEADER)
    lines.append("")
    lines.append("Cant Detalle                         Dinero")
    lines.append("=" * RECEIPT_WIDTH)

    for item in order.items:
        lines.extend(_item_lines(item.quantity, item.product_name, item.subtotal_cop))

    if order.delivery_price_cop > 0:
        delivery_name = f"Domicilio {order.neighborhood}".strip()
        lines.extend(_item_lines(1, delivery_name, order.delivery_price_cop))

    lines.append("=" * RECEIPT_WIDTH)
    lines.append(_row("*** TOTAL ***", _money(order.total_cop)))
    lines.append(_row(order.payment_method, _money(order.total_cop)))
    lines.append(_row("Completo", "0"))
    lines.append("")
    lines.append(f"FECHA: {created_at:%d/%m/%Y}")
    lines.append(f"HORA: {created_at:%H:%M:%S}")
    lines.append("")

    customer_lines = [
        ("Cliente", order.customer_name),
        ("Telefono", order.phone),
        ("Direccion", order.address),
        ("Barrio", order.neighborhood),
        ("Nota", order.observations or "Sin nota"),
    ]
    for label, value in customer_lines:
        lines.extend(_wrap(f"{label}: {value}", RECEIPT_WIDTH))

    lines.append("")
    lines.append(_center("<<< REGIMEN SIMPLIFICADO >>>"))
    lines.append(_center("GRACIAS POR SU COMPRA"))
    return "\n".join(_plain(line) for line in lines)


def _item_lines(quantity: int, name: str, total: int) -> list[str]:
    quantity_text = str(quantity)
    money = _money(total)
    name_width = max(12, RECEIPT_WIDTH - len(quantity_text) - len(money) - 2)
    wrapped = _wrap(name, name_width)
    first = f"{quantity_text} {wrapped[0].ljust(name_width)} {money}"
    return [first, *[f"  {line}" for line in wrapped[1:]]]


def _row(left: str, right: str) -> str:
    clean_left = _plain(left)
    clean_right = _plain(right)
    spaces = max(1, RECEIPT_WIDTH - len(clean_left) - len(clean_right))
    return f"{clean_left}{' ' * spaces}{clean_right}"


def _wrap(value: str, width: int) -> list[str]:
    words = _plain(value).split()
    lines: list[str] = []
    current = ""
    for word in words:
        if len(word) > width:
            if current:
                lines.append(current)
                current = ""
            lines.extend(word[index:index + width] for index in range(0, len(word), width))
            continue
        candidate = f"{current} {word}".strip()
        if len(candidate) > width:
            lines.append(current)
            current = word
        else:
            current = candidate
    if current:
        lines.append(current)
    return lines or [""]


def _center(value: str) -> str:
    plain = _plain(value)
    return plain.center(RECEIPT_WIDTH)


def _plain(value: str) -> str:
    normalized = unicodedata.normalize("NFKD", str(value))
    ascii_value = normalized.encode("ascii", errors="ignore").decode("ascii")
    return " ".join(ascii_value.replace("\r", " ").replace("\n", " ").split())


def _ascii(value: str) -> bytes:
    return value.encode("ascii", errors="replace")


def _money(value: int) -> str:
    return f"{int(value):,}".replace(",", ".")


def _local_datetime(value: datetime) -> datetime:
    if value.tzinfo is None:
        value = value.replace(tzinfo=ZoneInfo("UTC"))
    return value.astimezone(ZoneInfo("America/Bogota"))
