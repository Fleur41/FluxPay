package com.fluxpay.core.network.adapter

import com.squareup.moshi.FromJson
import com.squareup.moshi.ToJson
import java.math.BigDecimal
import java.time.Instant
import java.time.OffsetDateTime

/** DRF sends money as strings ("1250.00") to avoid floating point errors — keep it that way. */
class BigDecimalAdapter {
    @FromJson
    fun fromJson(value: String): BigDecimal = BigDecimal(value)

    @ToJson
    fun toJson(value: BigDecimal): String = value.toPlainString()
}

/** DRF datetimes are ISO-8601, e.g. "2026-10-03T11:26:00.123456Z". */
class InstantAdapter {
    @FromJson
    fun fromJson(value: String): Instant = OffsetDateTime.parse(value).toInstant()

    @ToJson
    fun toJson(value: Instant): String = value.toString()
}
