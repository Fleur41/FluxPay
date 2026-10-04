package com.fluxpay.feature.transactions.presentation.viewmodel

import androidx.lifecycle.ViewModel
import androidx.lifecycle.viewModelScope
import com.fluxpay.core.common.result.NetworkResult
import com.fluxpay.core.domain.model.StatementFormat
import com.fluxpay.core.domain.usecase.ObservePlatformConfigUseCase
import com.fluxpay.feature.transactions.domain.model.StatementRange
import com.fluxpay.feature.transactions.domain.usecase.DownloadStatementUseCase
import com.fluxpay.feature.transactions.presentation.state.StatementUiState
import dagger.hilt.android.lifecycle.HiltViewModel
import java.time.LocalDate
import javax.inject.Inject
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.asStateFlow
import kotlinx.coroutines.flow.filterNotNull
import kotlinx.coroutines.flow.launchIn
import kotlinx.coroutines.flow.onEach
import kotlinx.coroutines.flow.update
import kotlinx.coroutines.launch

@HiltViewModel
class StatementViewModel @Inject constructor(
    private val downloadStatement: DownloadStatementUseCase,
    observeConfig: ObservePlatformConfigUseCase,
) : ViewModel() {

    private val _state = MutableStateFlow(StatementUiState(period = StatementRange.THIS_MONTH.period(LocalDate.now())))
    val state: StateFlow<StatementUiState> = _state.asStateFlow()

    init {
        observeConfig().filterNotNull().onEach { config ->
            val today = LocalDate.now()
            val allowed = StatementRange.allowed(today, config.statementMaxDays)
            _state.update { s ->
                val range = s.range.takeIf { it in allowed } ?: allowed.firstOrNull() ?: s.range
                s.copy(ranges = allowed, range = range, period = range.period(today))
            }
        }.launchIn(viewModelScope)
    }

    fun onRangeChange(range: StatementRange) = _state.update {
        it.copy(range = range, period = range.period(LocalDate.now()), downloaded = null, error = null)
    }

    fun onFormatChange(format: StatementFormat) = _state.update { it.copy(format = format, downloaded = null, error = null) }

    fun download() {
        val current = _state.value
        if (current.isDownloading) return
        _state.update { it.copy(isDownloading = true, downloaded = null, error = null) }
        viewModelScope.launch {
            when (val result = downloadStatement(current.period, current.format)) {
                is NetworkResult.Success -> _state.update { it.copy(isDownloading = false, downloaded = result.data) }
                is NetworkResult.Error -> _state.update { it.copy(isDownloading = false, error = result.message) }
                NetworkResult.Loading -> Unit
            }
        }
    }

    /** Opening the file failed on this phone (e.g. no PDF viewer); shown in the sheet. */
    fun onOpenFailed(message: String) = _state.update { it.copy(error = message) }

    fun reset() = _state.update { s ->
        val range = s.ranges.firstOrNull() ?: StatementRange.THIS_MONTH
        StatementUiState(ranges = s.ranges, range = range, period = range.period(LocalDate.now()))
    }
}
