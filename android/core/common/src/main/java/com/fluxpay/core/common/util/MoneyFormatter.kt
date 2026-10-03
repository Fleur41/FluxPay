package com.fluxpay.core.common.util

import java.math.BigDecimal
import java.math.RoundingMode
import java.text.NumberFormat
import java.time.Instant
import java.time.LocalDate
import java.time.ZoneId
import java.time.format.DateTimeFormatter
import java.time.format.FormatStyle
import java.util.Currency
import java.util.Locale

object MoneyFormatter {
    const val MASK = "••••••"

    fun format(amount: BigDecimal, currencyCode: String, locale: Locale = Locale.getDefault()): String {
        val format = NumberFormat.getCurrencyInstance(locale)
        runCatching { format.currency = Currency.getInstance(currencyCode) }
        format.minimumFractionDigits = 2
        format.maximumFractionDigits = 2
        return format.format(amount.setScale(2, RoundingMode.HALF_EVEN))
    }

    fun formatSigned(amount: BigDecimal, currencyCode: String, isCredit: Boolean): String =
        (if (isCredit) "+" else "−") + format(amount.abs(), currencyCode)

    /** Parses user input like "1,250.5" into a 2-dp BigDecimal, or null if it's not a number. */
    fun parse(input: String): BigDecimal? = input
        .replace(",", "")
        .trim()
        .takeIf { it.isNotEmpty() }
        ?.toBigDecimalOrNull()
        ?.takeIf { it.scale() <= 2 }
        ?.setScale(2, RoundingMode.UNNECESSARY)
}

fun String.maskAccountNumber(): String = if (length <= 4) this else "•••• " + takeLast(4)

object DateFormatter {
    private val dateTime = DateTimeFormatter.ofLocalizedDateTime(FormatStyle.MEDIUM, FormatStyle.SHORT)
    private val time = DateTimeFormatter.ofLocalizedTime(FormatStyle.SHORT)
    private val date = DateTimeFormatter.ofLocalizedDate(FormatStyle.MEDIUM)

    fun dateTime(instant: Instant, zone: ZoneId = ZoneId.systemDefault()): String = dateTime.format(instant.atZone(zone))

    fun time(instant: Instant, zone: ZoneId = ZoneId.systemDefault()): String = time.format(instant.atZone(zone))

    /** "Today", "Yesterday" or a medium date — used for list section headers. */
    fun dayHeader(day: LocalDate, today: LocalDate = LocalDate.now()): String = when (day) {
        today -> "Today"
        today.minusDays(1) -> "Yesterday"
        else -> date.format(day)
    }
}
