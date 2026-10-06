package com.fluxpay.feature.transfer.presentation

import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.imePadding
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.verticalScroll
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.automirrored.filled.ArrowBack
import androidx.compose.material.icons.outlined.AccountBalanceWallet
import androidx.compose.material.icons.outlined.CheckCircle
import androidx.compose.material.icons.outlined.PhoneAndroid
import androidx.compose.material3.ExperimentalMaterial3Api
import androidx.compose.material3.Icon
import androidx.compose.material3.IconButton
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Scaffold
import androidx.compose.material3.Text
import androidx.compose.material3.TopAppBar
import androidx.compose.runtime.Composable
import androidx.compose.runtime.getValue
import androidx.compose.ui.Modifier
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.text.input.ImeAction
import androidx.compose.ui.text.input.KeyboardType
import androidx.compose.ui.text.style.TextAlign
import androidx.compose.ui.unit.dp
import androidx.hilt.navigation.compose.hiltViewModel
import androidx.lifecycle.compose.collectAsStateWithLifecycle
import com.fluxpay.core.common.util.MoneyFormatter
import com.fluxpay.core.ui.components.EmptyState
import com.fluxpay.core.ui.components.ErrorBanner
import com.fluxpay.core.ui.components.FluxPrimaryButton
import com.fluxpay.core.ui.components.FluxTextField
import com.fluxpay.feature.transfer.presentation.biometric.BiometricAuthenticator
import com.fluxpay.feature.transfer.presentation.biometric.findFragmentActivity
import com.fluxpay.feature.transfer.presentation.components.SourceAccountPicker
import com.fluxpay.feature.transfer.presentation.viewmodel.MpesaWithdrawViewModel

/** From the FluxPay wallet to the user's own M-Pesa number, confirmed with fingerprint or PIN like a transfer. */
@OptIn(ExperimentalMaterial3Api::class)
@Composable
fun MpesaWithdrawScreen(onBack: () -> Unit, onDone: () -> Unit, viewModel: MpesaWithdrawViewModel = hiltViewModel()) {
    val state by viewModel.state.collectAsStateWithLifecycle()
    val context = LocalContext.current
    val confirmAndSend: () -> Unit = confirm@{
        if (!viewModel.validate()) return@confirm
        val wallet = state.wallet ?: return@confirm
        val activity = context.findFragmentActivity()
        when (val availability = BiometricAuthenticator.availability(context)) {
            is BiometricAuthenticator.Availability.Unavailable -> viewModel.onAuthenticationFailed(availability.reason)
            BiometricAuthenticator.Availability.Available -> if (activity != null) {
                BiometricAuthenticator.authenticate(
                    activity = activity,
                    title = "Send to M-Pesa",
                    subtitle = "${MoneyFormatter.format(state.amountText.toBigDecimal(), wallet.currency)} to ${state.phoneNumber}",
                    onSuccess = viewModel::onAuthenticated,
                    onError = viewModel::onAuthenticationFailed,
                )
            }
        }
    }
    Scaffold(
        topBar = {
            TopAppBar(
                title = { Text(if (state.sent == null) "Send to M-Pesa" else "Done") },
                navigationIcon = { IconButton(onClick = onBack) { Icon(Icons.AutoMirrored.Filled.ArrowBack, "Back") } },
            )
        },
    ) { padding ->
        Column(
            Modifier.padding(padding).fillMaxSize().imePadding().verticalScroll(rememberScrollState())
                .padding(horizontal = 20.dp, vertical = 8.dp),
            verticalArrangement = Arrangement.spacedBy(14.dp),
        ) {
            state.errorMessage?.let { ErrorBanner(it) }
            val sent = state.sent
            when {
                sent != null -> {
                    Icon(Icons.Outlined.CheckCircle, null, Modifier.fillMaxWidth(), tint = MaterialTheme.colorScheme.primary)
                    Text(MoneyFormatter.format(sent.amount, sent.currency), Modifier.fillMaxWidth(),
                        style = MaterialTheme.typography.displaySmall, textAlign = TextAlign.Center)
                    Text("On its way to ${state.phoneNumber}. M-Pesa usually confirms within a minute; you'll get their SMS. " +
                        "If M-Pesa can't pay it, the money comes back to your wallet.",
                        style = MaterialTheme.typography.bodyMedium, textAlign = TextAlign.Center, modifier = Modifier.fillMaxWidth())
                    Text("Reference ${sent.reference}", style = MaterialTheme.typography.bodySmall,
                        color = MaterialTheme.colorScheme.onSurfaceVariant, textAlign = TextAlign.Center, modifier = Modifier.fillMaxWidth())
                    FluxPrimaryButton("Done", onDone)
                }
                state.wallets.isEmpty() -> EmptyState(Icons.Outlined.AccountBalanceWallet, "No KES wallet",
                    "M-Pesa pays out in Kenyan shillings, so you need a KES wallet.")
                else -> {
                    Text("Move money from FluxPay to your own M-Pesa, to spend it or save it there.",
                        style = MaterialTheme.typography.bodyMedium, color = MaterialTheme.colorScheme.onSurfaceVariant)
                    SourceAccountPicker(state.wallets, state.wallet, hideBalances = false, onSelect = viewModel::onWalletSelected, error = null)
                    FluxTextField(
                        value = state.phoneNumber.ifBlank { "No number on your profile" },
                        onValueChange = {},
                        label = "To M-Pesa number",
                        supportingText = "For your safety, money only goes to the number on your profile.",
                        leadingIcon = Icons.Outlined.PhoneAndroid,
                        enabled = false,
                    )
                    FluxTextField(
                        value = state.amountText,
                        onValueChange = viewModel::onAmountChange,
                        label = "Amount",
                        error = state.amountError,
                        supportingText = "Whole shillings",
                        keyboardType = KeyboardType.Number,
                        prefix = "KES ",
                        imeAction = ImeAction.Done,
                        onImeAction = confirmAndSend,
                    )
                    FluxPrimaryButton("Send to M-Pesa", confirmAndSend, enabled = state.amountText.isNotEmpty(), loading = state.isWorking)
                }
            }
        }
    }
}
