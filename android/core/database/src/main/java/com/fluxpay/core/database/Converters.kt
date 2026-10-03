package com.fluxpay.core.database

import androidx.room.TypeConverter
import java.math.BigDecimal
import java.time.Instant

/** Money is stored as TEXT (never REAL) so balances keep exact cents. */
class Converters {
    @TypeConverter
    fun bigDecimalToString(value: BigDecimal?): String? = value?.toPlainString()

    @TypeConverter
    fun stringToBigDecimal(value: String?): BigDecimal? = value?.let(::BigDecimal)

    @TypeConverter
    fun instantToEpochMillis(value: Instant?): Long? = value?.toEpochMilli()

    @TypeConverter
    fun epochMillisToInstant(value: Long?): Instant? = value?.let(Instant::ofEpochMilli)
}
