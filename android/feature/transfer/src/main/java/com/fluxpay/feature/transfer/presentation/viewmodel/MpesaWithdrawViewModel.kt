package com.fluxpay.feature.transfer.presentation.viewmodel

import androidx.lifecycle.ViewModel
import androidx.lifecycle.viewModelScope
import com.fluxpay.core.common.result.NetworkResult
import com.fluxpay.core.domain.model.Account
import com.fluxpay.core.domain.model.MpesaWithdrawal
import com.fluxpay.core.domain.repository.AuthRepository
import com.fluxpay.core.domain.repository.TransferRepository
import com.fluxpay.core.domain.usecase.ObserveAccountsUseCase
import dagger.hilt.android.lifecycle.HiltViewModel
import java.util.UUID
import javax.inject.Inject
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.asStateFlow
import kotlinx.coroutines.flow.combine
import kotlinx.coroutines.flow.launchIn
import kotlinx.coroutines.flow.onEach
import kotlinx.coroutines.flow.update
import kotlinx.coroutines.launch

data class MpesaWithdrawUiState(
    /** M-Pesa pays out shillings only, so only KES wallets. */
    val wallets: List<Account> = emptyList(),
    val selectedWalletId: String? = null,
    /** The number on the user's profile: the only one the server sends to. */
    val phoneNumber: String = "",
    val amountText: String = "",
    val amountError: String? = null,
    val isWorking: Boolean = false,
    val errorMessage: String? = null,
    /** Fixed when the form is filled, so a retry after a dropped connection can't pay twice. */
    val idempotencyKey: String = UUID.randomUUID().toString(),
    val sent: MpesaWithdrawal? = null,
) {
    val wallet: Account? get() = wallets.firstOrNull { it.id == selectedWalletId }
}

/** The worker's way out: from their FluxPay wallet to their own M-Pesa, e.g. to save or spend it there. */
@HiltViewModel
class MpesaWithdrawViewModel @Inject constructor(
    observeAccounts: ObserveAccountsUseCase,
    auth: AuthRepository,
    private val transfers: TransferRepository,
) : ViewModel() {
    private val _state = MutableStateFlow(MpesaWithdrawUiState())
    val state: StateFlow<MpesaWithdrawUiState> = _state.asStateFlow()

    init {
        combine(observeAccounts(), auth.observeProfile()) { accounts, user -> accounts.filter { it.currency == "KES" } to user }
            .onEach { (wallets, user) ->
                _state.update { s ->
                    s.copy(
                        wallets = wallets,
                        selectedWalletId = s.selectedWalletId?.takeIf { id -> wallets.any { it.id == id } } ?: wallets.firstOrNull()?.id,
                        phoneNumber = user?.phoneNumber.orEmpty(),
                    )
                }
            }
            .launchIn(viewModelScope)
    }

    fun onWalletSelected(id: String) = _state.update { it.copy(selectedWalletId = id) }

    fun onAmountChange(value: String) = _state.update {
        it.copy(amountText = value.filter(Char::isDigit).take(9), amountError = null, errorMessage = null)
    }

    /** Checks the form; true when it's ready for the fingerprint/PIN confirmation. */
    fun validate(): Boolean {
        val s = _state.value
        val wallet = s.wallet
        val amount = s.amountText.toBigDecimalOrNull()
        val error = when {
            wallet == null -> "You need a KES wallet to send to M-Pesa."
            s.phoneNumber.isBlank() -> "Add your M-Pesa number to your profile first."
            amount == null || amount.signum() <= 0 -> "Enter an amount in whole shillings."
            amount > wallet.balance -> "Your wallet has ${wallet.balance.toPlainString()} ${wallet.currency}."
            else -> null
        }
        _state.update { it.copy(amountError = error) }
        return error == null
    }

    /** Called only after the fingerprint/PIN prompt succeeds. */
    fun onAuthenticated() {
        val s = _state.value
        val wallet = s.wallet ?: return
        val amount = s.amountText.toBigDecimalOrNull() ?: return
        if (s.isWorking) return
        _state.update { it.copy(isWorking = true, errorMessage = null) }
        viewModelScope.launch {
            when (val result = transfers.withdrawToMpesa(wallet.id, amount, s.idempotencyKey)) {
                is NetworkResult.Success -> _state.update { it.copy(isWorking = false, sent = result.data) }
                is NetworkResult.Error -> _state.update { it.copy(isWorking = false, errorMessage = result.message) }
                NetworkResult.Loading -> Unit
            }
        }
    }

    fun onAuthenticationFailed(message: String) = _state.update { it.copy(errorMessage = message) }
}
