package com.fluxpay.core.common.util

// Plain regex (not android.util.Patterns) so validation is testable in JVM unit tests.
private val EMAIL_REGEX = Regex("^[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\\.[A-Za-z]{2,}$")

fun String.isValidEmail(): Boolean = EMAIL_REGEX.matches(trim())

fun String.isValidAccountNumber(): Boolean = length == 10 && all(Char::isDigit) && first() != '0'

fun String.initials(): String = trim()
    .split(Regex("\\s+"))
    .filter { it.isNotEmpty() }
    .take(2)
    .joinToString("") { it.first().uppercase() }
    .ifEmpty { "?" }
