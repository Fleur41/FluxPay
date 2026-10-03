package com.fluxpay.feature.transfer.presentation

import androidx.activity.compose.BackHandler
import androidx.compose.foundation.background
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.imePadding
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.shape.CircleShape
import androidx.compose.foundation.verticalScroll
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.automirrored.filled.ArrowBack
import androidx.compose.material.icons.outlined.AccountBalanceWallet
import androidx.compose.material.icons.outlined.Check
import androidx.compose.material.icons.outlined.Description
import androidx.compose.material.icons.outlined.Fingerprint
import androidx.compose.material.icons.outlined.Numbers
import androidx.compose.material3.ExperimentalMaterial3Api
import androidx.compose.material3.Icon
import androidx.compose.material3.IconButton
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Scaffold
import androidx.compose.material3.Text
import androidx.compose.material3.TopAppBar
import androidx.compose.runtime.Composable
import androidx.compose.runtime.getValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.clip
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.text.input.ImeAction
import androidx.compose.ui.text.input.KeyboardType
import androidx.compose.ui.text.style.TextAlign
import androidx.compose.ui.unit.dp
import androidx.hilt.navigation.compose.hiltViewModel
import androidx.lifecycle.compose.collectAsStateWithLifecycle
import com.fluxpay.core.common.util.DateFormatter
import com.fluxpay.core.common.util.MoneyFormatter
import com.fluxpay.core.ui.components.EmptyState
import com.fluxpay.core.ui.components.ErrorBanner
import com.fluxpay.core.ui.components.FluxPrimaryButton
import com.fluxpay.core.ui.components.FluxSecondaryButton
import com.fluxpay.core.ui.components.FluxTextField
import com.fluxpay.core.ui.theme.FluxTheme
import com.fluxpay.feature.transfer.presentation.biometric.BiometricAuthenticator
import com.fluxpay.feature.transfer.presentation.biometric.findFragmentActivity
import com.fluxpay.feature.transfer.presentation.components.RecipientCard
import com.fluxpay.feature.transfer.presentation.components.SourceAccountPicker
import com.fluxpay.feature.transfer.presentation.state.TransferStep
import com.fluxpay.feature.transfer.presentation.state.TransferUiState
import com.fluxpay.feature.transfer.presentation.viewmodel.TransferViewModel

@OptIn(ExperimentalMaterial3Api::class)
@Composable
fun TransferScreen(
    onDone: () -> Unit,
    onViewTransaction: (String) -> Unit,
    viewModel: TransferViewModel = hiltViewModel(),
) {
    val state by viewModel.state.collectAsStateWithLifecycle()
    val context = LocalContext.current
    val step = state.step

    BackHandler(enabled = step is TransferStep.Review) { viewModel.onEdit() }

    val authenticateAndSend: () -> Unit = {
        val activity = context.findFragmentActivity()
        when (val availability = BiometricAuthenticator.availability(context)) {
            is BiometricAuthenticator.Availability.Unavailable -> viewModel.onAuthenticationFailed(availability.reason)
            BiometricAuthenticator.Availability.Available -> if (activity != null) {
                val review = step as TransferStep.Review
                BiometricAuthenticator.authenticate(
                    activity = activity,
                    title = "Confirm transfer",
                    subtitle = "Send ${MoneyFormatter.format(review.amount, review.source.currency)} to ${review.recipient.holderName}",
                    onSuccess = viewModel::onAuthenticated,
                    onError = viewModel::onAuthenticationFailed,
                )
            }
        }
    }

    Scaffold(
        topBar = {
            TopAppBar(
                title = {
                    Text(
                        when (step) {
                            TransferStep.Form -> "Send money"
                            is TransferStep.Review -> "Review transfer"
                            is TransferStep.Success -> "Done"
                        },
                    )
                },
                navigationIcon = {
                    if (step is TransferStep.Review) {
                        IconButton(onClick = viewModel::onEdit) { Icon(Icons.AutoMirrored.Filled.ArrowBack, "Edit") }
                    }
                },
            )
        },
    ) { padding ->
        Column(
            modifier = Modifier
                .padding(padding)
                .fillMaxSize()
                .imePadding()
                .verticalScroll(rememberScrollState())
                .padding(horizontal = 20.dp, vertical = 8.dp),
            verticalArrangement = Arrangement.spacedBy(14.dp),
        ) {
            state.errorMessage?.let { ErrorBanner(it) }
            when (step) {
                TransferStep.Form -> TransferForm(state, viewModel)
                is TransferStep.Review -> ReviewStep(step, state.isWorking, authenticateAndSend, viewModel::onEdit)
                is TransferStep.Success -> SuccessStep(
                    step = step,
                    onDone = {
                        viewModel.reset()
                        onDone()
                    },
                    onViewTransaction = {
                        val id = step.receipt.transaction.id
                        viewModel.reset()
                        onViewTransaction(id)
                    },
                )
            }
        }
    }
}

@Composable
private fun TransferForm(state: TransferUiState, viewModel: TransferViewModel) {
    if (state.accounts.isEmpty()) {
        EmptyState(
            icon = Icons.Outlined.AccountBalanceWallet,
            title = "No wallet yet",
            message = "Pull to refresh on the dashboard to load your wallets.",
        )
        return
    }
    SourceAccountPicker(
        accounts = state.accounts,
        selected = state.selectedAccount,
        hideBalances = state.hideBalances,
        onSelect = viewModel::onAccountSelected,
        error = state.errors.source,
    )
    FluxTextField(
        value = state.recipientNumber,
        onValueChange = viewModel::onRecipientChange,
        label = "Recipient account number",
        error = state.errors.recipient,
        supportingText = "10-digit FluxPay account number",
        keyboardType = KeyboardType.Number,
        leadingIcon = Icons.Outlined.Numbers,
    )
    FluxTextField(
        value = state.amountText,
        onValueChange = viewModel::onAmountChange,
        label = "Amount",
        error = state.errors.amount,
        keyboardType = KeyboardType.Decimal,
        prefix = state.selectedAccount?.currency?.let { "$it " },
    )
    FluxTextField(
        value = state.note,
        onValueChange = viewModel::onNoteChange,
        label = "Note (optional)",
        error = state.errors.note,
        supportingText = "${state.note.length}/140",
        imeAction = ImeAction.Done,
        onImeAction = viewModel::onContinue,
        leadingIcon = Icons.Outlined.Description,
    )
    FluxPrimaryButton(text = "Continue", onClick = viewModel::onContinue, loading = state.isWorking)
}

@Composable
private fun ReviewStep(
    review: TransferStep.Review,
    sending: Boolean,
    onConfirm: () -> Unit,
    onEdit: () -> Unit,
) {
    Text(
        MoneyFormatter.format(review.amount, review.source.currency),
        style = MaterialTheme.typography.displaySmall,
        modifier = Modifier.fillMaxWidth(),
        textAlign = TextAlign.Center,
    )
    RecipientCard(
        name = review.recipient.holderName,
        accountNumber = review.recipient.accountNumber,
        rows = buildList {
            add("From" to review.source.name)
            add("Fee" to "Free")
            if (review.note.isNotBlank()) add("Note" to review.note)
            add("Recipient gets" to MoneyFormatter.format(review.amount, review.recipient.currency))
        },
    )
    Text(
        "Check the name matches who you mean to pay. Transfers can't be reversed.",
        style = MaterialTheme.typography.bodySmall,
        color = MaterialTheme.colorScheme.onSurfaceVariant,
    )
    FluxPrimaryButton(text = "Confirm & send", onClick = onConfirm, loading = sending)
    Row(Modifier.fillMaxWidth(), horizontalArrangement = Arrangement.Center) {
        Icon(Icons.Outlined.Fingerprint, contentDescription = null, tint = MaterialTheme.colorScheme.onSurfaceVariant)
        Text(
            " You'll confirm with your fingerprint, face or screen lock",
            style = MaterialTheme.typography.bodySmall,
            color = MaterialTheme.colorScheme.onSurfaceVariant,
        )
    }
    FluxSecondaryButton(text = "Edit details", onClick = onEdit, enabled = !sending)
}

@Composable
private fun SuccessStep(step: TransferStep.Success, onDone: () -> Unit, onViewTransaction: () -> Unit) {
    val receipt = step.receipt
    Column(
        Modifier.fillMaxWidth().padding(top = 24.dp),
        horizontalAlignment = Alignment.CenterHorizontally,
        verticalArrangement = Arrangement.spacedBy(10.dp),
    ) {
        Box(
            Modifier.size(84.dp).clip(CircleShape).background(FluxTheme.colors.heroGradient),
            contentAlignment = Alignment.Center,
        ) {
            Icon(Icons.Outlined.Check, contentDescription = null, tint = Color.White, modifier = Modifier.size(44.dp))
        }
        Text("Money sent", style = MaterialTheme.typography.headlineSmall)
        Text(
            MoneyFormatter.format(receipt.amount, receipt.currency),
            style = MaterialTheme.typography.displaySmall,
        )
        Text(
            "to ${receipt.recipientName} · ${DateFormatter.dateTime(receipt.createdAt)}",
            style = MaterialTheme.typography.bodyMedium,
            color = MaterialTheme.colorScheme.onSurfaceVariant,
            textAlign = TextAlign.Center,
        )
        Text("Reference ${receipt.reference}", style = MaterialTheme.typography.labelLarge)
        Spacer(Modifier.height(16.dp))
        FluxPrimaryButton(text = "Done", onClick = onDone)
        FluxSecondaryButton(text = "View receipt", onClick = onViewTransaction)
    }
}
