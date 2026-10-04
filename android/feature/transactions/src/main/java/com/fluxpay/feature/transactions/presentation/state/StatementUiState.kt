package com.fluxpay.feature.transactions.presentation.state

import com.fluxpay.core.domain.model.DownloadedStatement
import com.fluxpay.core.domain.model.StatementFormat
import com.fluxpay.core.domain.model.StatementPeriod
import com.fluxpay.feature.transactions.domain.model.StatementRange

data class StatementUiState(
    /** Presets that fit the server's maximum statement length; all of them until the rules load. */
    val ranges: List<StatementRange> = StatementRange.entries,
    val range: StatementRange = StatementRange.THIS_MONTH,
    val period: StatementPeriod,
    val format: StatementFormat = StatementFormat.PDF,
    val isDownloading: Boolean = false,
    val downloaded: DownloadedStatement? = null,
    val error: String? = null,
)
