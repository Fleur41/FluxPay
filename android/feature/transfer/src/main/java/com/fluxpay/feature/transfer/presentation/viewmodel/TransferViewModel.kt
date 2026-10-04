package com.fluxpay.feature.transfer.presentation.viewmodel

import androidx.lifecycle.ViewModel
import androidx.lifecycle.viewModelScope
import com.fluxpay.core.common.result.NetworkResult
import com.fluxpay.core.domain.model.TransferRequest
import com.fluxpay.core.domain.usecase.ObserveAccountsUseCase
import com.fluxpay.core.domain.model.PlatformConfig
import com.fluxpay.core.domain.usecase.ObservePlatformConfigUseCase
import com.fluxpay.core.domain.usecase.ObservePreferencesUseCase
import com.fluxpay.feature.transfer.domain.usecase.LookupRecipientUseCase
import com.fluxpay.feature.transfer.domain.usecase.SendMoneyUseCase
import com.fluxpay.feature.transfer.domain.usecase.ValidateTransferUseCase
import com.fluxpay.feature.transfer.presentation.state.TransferStep
import com.fluxpay.feature.transfer.presentation.state.TransferUiState
import dagger.hilt.android.lifecycle.HiltViewModel
import java.util.UUID
import javax.inject.Inject
import kotlinx.coroutines.Job
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.asStateFlow
import kotlinx.coroutines.flow.combine
import kotlinx.coroutines.flow.launchIn
import kotlinx.coroutines.flow.onEach
import kotlinx.coroutines.flow.update
import kotlinx.coroutines.launch

@HiltViewModel
class TransferViewModel @Inject constructor(
    observeAccounts: ObserveAccountsUseCase,
    observePreferences: ObservePreferencesUseCase,
    observeConfig: ObservePlatformConfigUseCase,
    private val validate: ValidateTransferUseCase,
    private val lookupRecipient: LookupRecipientUseCase,
    private val sendMoney: SendMoneyUseCase,
) : ViewModel() {

    private val _state = MutableStateFlow(TransferUiState())
    val state: StateFlow<TransferUiState> = _state.asStateFlow()

    /** Held so it can be cancelled explicitly if the user backs out mid-request. */
    private var workJob: Job? = null

    /** Business rules from the server (per-currency limits); null until loaded. */
    @Volatile private var config: PlatformConfig? = null

    init {
        combine(observeAccounts(), observePreferences()) { accounts, prefs -> accounts to prefs }
            .onEach { (accounts, prefs) ->
                _state.update { s ->
                    s.copy(
                        accounts = accounts,
                        hideBalances = prefs.hideBalances,
                        selectedAccountId = s.selectedAccountId?.takeIf { id -> accounts.any { it.id == id } }
                            ?: (accounts.firstOrNull { it.currency == prefs.currency } ?: accounts.firstOrNull())?.id,
                    )
                }
            }
            .launchIn(viewModelScope)
        observeConfig().onEach { config = it }.launchIn(viewModelScope)
    }

    fun onAccountSelected(id: String) = _state.update { it.copy(selectedAccountId = id, errors = it.errors.copy(source = null)) }

    fun onRecipientChange(value: String) = _state.update {
        it.copy(recipientNumber = value.filter(Char::isDigit).take(10), errors = it.errors.copy(recipient = null), errorMessage = null)
    }

    fun onAmountChange(value: String) = _state.update {
        it.copy(amountText = value.filter { c -> c.isDigit() || c == '.' || c == ',' }, errors = it.errors.copy(amount = null))
    }

    fun onNoteChange(value: String) = _state.update { it.copy(note = value.take(140), errors = it.errors.copy(note = null)) }

    /** Form → validate locally → confirm recipient with the server → Review. */
    fun onContinue() {
        val s = _state.value
        if (s.isWorking) return
        val source = s.selectedAccount
        val rule = source?.let { config?.currency(it.currency) }
        val validation = validate(source, rule, s.recipientNumber, s.amountText, s.note)
        val amount = validation.amount
        if (source == null || amount == null) {
            _state.update { it.copy(errors = validation.errors) }
            return
        }
        _state.update { it.copy(isWorking = true, errorMessage = null) }
        workJob = viewModelScope.launch {
            when (val result = lookupRecipient(s.recipientNumber)) {
                is NetworkResult.Success -> {
                    val recipient = result.data
                    if (recipient.currency != source.currency) {
                        _state.update {
                            it.copy(
                                isWorking = false,
                                errors = it.errors.copy(
                                    recipient = "This account holds ${recipient.currency}; your wallet is ${source.currency}.",
                                ),
                            )
                        }
                    } else {
                        _state.update {
                            it.copy(
                                isWorking = false,
                                step = TransferStep.Review(
                                    source = source,
                                    recipient = recipient,
                                    amount = amount,
                                    note = s.note.trim(),
                                    idempotencyKey = UUID.randomUUID().toString(),
                                ),
                            )
                        }
                    }
                }
                is NetworkResult.Error -> _state.update {
                    if (result.httpStatus == 404) {
                        it.copy(isWorking = false, errors = it.errors.copy(recipient = result.message))
                    } else {
                        it.copy(isWorking = false, errorMessage = result.message)
                    }
                }
                NetworkResult.Loading -> Unit
            }
        }
    }

    fun onEdit() {
        workJob?.cancel()
        _state.update { it.copy(step = TransferStep.Form, isWorking = false, errorMessage = null) }
    }

    /** Called only after BiometricPrompt reports success. */
    fun onAuthenticated() {
        val review = _state.value.step as? TransferStep.Review ?: return
        if (_state.value.isWorking) return
        val request = TransferRequest.builder()
            .from(review.source.id)
            .to(review.recipient.accountNumber)
            .amount(review.amount)
            .note(review.note)
            .idempotencyKey(review.idempotencyKey)
            .build()
        _state.update { it.copy(isWorking = true, errorMessage = null) }
        workJob = viewModelScope.launch {
            when (val result = sendMoney(request)) {
                is NetworkResult.Success -> _state.update {
                    it.copy(isWorking = false, step = TransferStep.Success(result.data))
                }
                is NetworkResult.Error -> _state.update { it.copy(isWorking = false, errorMessage = result.message) }
                NetworkResult.Loading -> Unit
            }
        }
    }

    fun onAuthenticationFailed(message: String) = _state.update { it.copy(errorMessage = message) }

    /** After success: clear the form for the next transfer. */
    fun reset() = _state.update { s ->
        TransferUiState(accounts = s.accounts, selectedAccountId = s.selectedAccountId, hideBalances = s.hideBalances)
    }
}
