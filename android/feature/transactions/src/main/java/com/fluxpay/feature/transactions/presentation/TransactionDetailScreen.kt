package com.fluxpay.feature.transactions.presentation

import android.content.Intent
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.verticalScroll
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.automirrored.filled.ArrowBack
import androidx.compose.material.icons.outlined.SearchOff
import androidx.compose.material.icons.outlined.Share
import androidx.compose.material3.Card
import androidx.compose.material3.ExperimentalMaterial3Api
import androidx.compose.material3.HorizontalDivider
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
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.unit.dp
import androidx.lifecycle.compose.collectAsStateWithLifecycle
import com.fluxpay.core.common.util.DateFormatter
import com.fluxpay.core.common.util.MoneyFormatter
import com.fluxpay.core.domain.model.Transaction
import com.fluxpay.core.domain.model.TransactionCategory
import com.fluxpay.core.ui.components.EmptyState
import com.fluxpay.core.ui.components.ErrorBanner
import com.fluxpay.core.ui.components.FullScreenLoading
import com.fluxpay.core.ui.components.MoneyText
import com.fluxpay.core.ui.theme.FluxTheme
import com.fluxpay.feature.transactions.presentation.components.DetailRow
import com.fluxpay.feature.transactions.presentation.components.StatusChip
import com.fluxpay.feature.transactions.presentation.viewmodel.TransactionDetailViewModel

@OptIn(ExperimentalMaterial3Api::class)
@Composable
fun TransactionDetailScreen(
    viewModel: TransactionDetailViewModel,
    onBack: () -> Unit,
) {
    val state by viewModel.state.collectAsStateWithLifecycle()
    val context = LocalContext.current
    val transaction = state.transaction

    Scaffold(
        topBar = {
            TopAppBar(
                title = { Text("Transaction") },
                navigationIcon = {
                    IconButton(onClick = onBack) { Icon(Icons.AutoMirrored.Filled.ArrowBack, "Back") }
                },
                actions = {
                    if (transaction != null) {
                        IconButton(
                            onClick = {
                                // The Context is only used for this click; it's never stored.
                                val share = Intent(Intent.ACTION_SEND)
                                    .setType("text/plain")
                                    .putExtra(Intent.EXTRA_TEXT, transaction.toReceiptText())
                                context.startActivity(Intent.createChooser(share, "Share receipt"))
                            },
                        ) { Icon(Icons.Outlined.Share, "Share receipt") }
                    }
                },
            )
        },
    ) { padding ->
        when {
            transaction != null -> TransactionDetailContent(transaction, state.hideAmounts, Modifier.padding(padding))
            state.isLoading -> FullScreenLoading(Modifier.padding(padding))
            else -> Column(Modifier.padding(padding).padding(16.dp)) {
                state.error?.let { ErrorBanner(it.message, offline = it.isNetworkFailure, onRetry = viewModel::retry) }
                EmptyState(Icons.Outlined.SearchOff, "Transaction not found", "It may belong to another account.")
            }
        }
    }
}

@Composable
private fun TransactionDetailContent(transaction: Transaction, hideAmounts: Boolean, modifier: Modifier) {
    Column(
        modifier = modifier.fillMaxSize().verticalScroll(rememberScrollState()).padding(20.dp),
        horizontalAlignment = Alignment.CenterHorizontally,
        verticalArrangement = Arrangement.spacedBy(8.dp),
    ) {
        Text(
            transaction.counterpartyName.ifBlank { "FluxPay" },
            style = MaterialTheme.typography.titleMedium,
            color = MaterialTheme.colorScheme.onSurfaceVariant,
        )
        MoneyText(
            amount = transaction.amount,
            currency = transaction.currency,
            hidden = hideAmounts,
            signedCredit = transaction.isCredit,
            style = MaterialTheme.typography.displaySmall,
            color = if (transaction.isCredit) FluxTheme.colors.credit else MaterialTheme.colorScheme.onSurface,
        )
        StatusChip(transaction.status)
        Spacer(Modifier.height(8.dp))
        Card(Modifier.fillMaxWidth()) {
            Column(Modifier.padding(horizontal = 16.dp, vertical = 6.dp)) {
                DetailRow("Type", transaction.category.label())
                HorizontalDivider()
                DetailRow("Date", DateFormatter.dateTime(transaction.createdAt))
                HorizontalDivider()
                if (transaction.counterpartyAccount.isNotBlank()) {
                    DetailRow(if (transaction.isCredit) "From account" else "To account", transaction.counterpartyAccount)
                    HorizontalDivider()
                }
                if (transaction.description.isNotBlank()) {
                    DetailRow("Note", transaction.description)
                    HorizontalDivider()
                }
                DetailRow(
                    "Balance after",
                    if (hideAmounts) MoneyFormatter.MASK else MoneyFormatter.format(transaction.balanceAfter, transaction.currency),
                )
                HorizontalDivider()
                DetailRow("Reference", transaction.reference)
            }
        }
    }
}

private fun TransactionCategory.label() = when (this) {
    TransactionCategory.TRANSFER_IN -> "Money received"
    TransactionCategory.TRANSFER_OUT -> "Money sent"
    TransactionCategory.BONUS -> "Bonus"
    TransactionCategory.DEPOSIT -> "Deposit"
    TransactionCategory.WITHDRAWAL -> "Withdrawal"
    TransactionCategory.WITHDRAWAL_REVERSAL -> "Money returned"
    TransactionCategory.ADJUSTMENT -> "Top-up / correction by FluxPay"
    TransactionCategory.UNKNOWN -> "Other"
}

private fun Transaction.toReceiptText(): String = buildString {
    appendLine("FluxPay receipt")
    appendLine(if (isCredit) "Received from $counterpartyName" else "Sent to $counterpartyName")
    appendLine("Amount: ${MoneyFormatter.format(amount, currency)}")
    appendLine("Date: ${DateFormatter.dateTime(createdAt)}")
    if (description.isNotBlank()) appendLine("Note: $description")
    append("Reference: $reference")
}
