package com.fluxpay.feature.dashboard.presentation

import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.PaddingValues
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.statusBarsPadding
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.automirrored.outlined.CallReceived
import androidx.compose.material.icons.automirrored.outlined.ReceiptLong
import androidx.compose.material.icons.automirrored.outlined.Send
import androidx.compose.material.icons.outlined.History
import androidx.compose.material3.ExperimentalMaterial3Api
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Text
import androidx.compose.material3.TextButton
import androidx.compose.material3.pulltorefresh.PullToRefreshBox
import androidx.compose.runtime.Composable
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.saveable.rememberSaveable
import androidx.compose.runtime.setValue
import androidx.compose.ui.Modifier
import androidx.compose.ui.unit.dp
import androidx.hilt.navigation.compose.hiltViewModel
import androidx.lifecycle.compose.collectAsStateWithLifecycle
import com.fluxpay.core.domain.model.Transaction
import com.fluxpay.core.ui.adapter.recentTransactionItems
import com.fluxpay.core.ui.components.BalanceCard
import com.fluxpay.core.ui.components.EmptyState
import com.fluxpay.core.ui.components.ErrorBanner
import com.fluxpay.core.ui.components.FullScreenLoading
import com.fluxpay.core.ui.components.SectionTitle
import com.fluxpay.feature.dashboard.presentation.components.AccountsRow
import com.fluxpay.feature.dashboard.presentation.components.BudgetPlannerCard
import com.fluxpay.feature.dashboard.presentation.components.QuickAction
import com.fluxpay.feature.dashboard.presentation.components.QuickActionsRow
import com.fluxpay.feature.dashboard.presentation.components.ReceiveSheet
import com.fluxpay.feature.dashboard.presentation.viewmodel.DashboardViewModel
import java.time.LocalTime

@OptIn(ExperimentalMaterial3Api::class)
@Composable
fun DashboardScreen(
    onSendMoney: () -> Unit,
    onSeeAllTransactions: () -> Unit,
    onTransactionClick: (Transaction) -> Unit,
    onOpenBudget: () -> Unit,
    viewModel: DashboardViewModel = hiltViewModel(),
) {
    val state by viewModel.state.collectAsStateWithLifecycle()
    val summary = state.summary
    var showReceive by rememberSaveable { mutableStateOf(false) }

    if (summary == null) {
        FullScreenLoading()
        return
    }

    PullToRefreshBox(
        isRefreshing = state.isRefreshing,
        onRefresh = viewModel::refresh,
        modifier = Modifier.fillMaxSize(),
    ) {
        LazyColumn(
            modifier = Modifier.fillMaxSize().statusBarsPadding(),
            contentPadding = PaddingValues(bottom = 24.dp),
        ) {
            item(key = "header") {
                Column(Modifier.padding(horizontal = 20.dp, vertical = 16.dp)) {
                    Text(
                        greeting(),
                        style = MaterialTheme.typography.bodyLarge,
                        color = MaterialTheme.colorScheme.onSurfaceVariant,
                    )
                    Text(
                        summary.firstName.ifBlank { "there" },
                        style = MaterialTheme.typography.headlineMedium,
                    )
                }
            }
            state.error?.let { error ->
                item(key = "error") {
                    ErrorBanner(
                        message = error.message,
                        offline = error.isNetworkFailure,
                        onRetry = viewModel::refresh,
                        modifier = Modifier.padding(horizontal = 20.dp, vertical = 4.dp),
                    )
                }
            }
            // No balance card until a wallet has synced: there is no currency to total in yet.
            summary.totalCurrency?.let { totalCurrency ->
                item(key = "balance") {
                    BalanceCard(
                        title = "Total balance",
                        amount = summary.totalBalance,
                        currency = totalCurrency,
                        hidden = summary.hideBalances,
                        onToggleHidden = viewModel::toggleHideBalances,
                        footer = when {
                            summary.otherCurrencyAccounts > 0 ->
                                "+ ${summary.otherCurrencyAccounts} wallet(s) in other currencies"
                            summary.accounts.size == 1 -> summary.accounts.first().name
                            else -> "Across ${summary.accounts.size} wallets"
                        },
                        modifier = Modifier.padding(horizontal = 20.dp, vertical = 8.dp),
                    )
                }
            }
            item(key = "actions") {
                QuickActionsRow(Modifier.padding(horizontal = 20.dp, vertical = 8.dp)) { weight ->
                    QuickAction(Icons.AutoMirrored.Outlined.Send, "Send", onSendMoney, weight)
                    QuickAction(Icons.AutoMirrored.Outlined.CallReceived, "Receive", { showReceive = true }, weight)
                    QuickAction(Icons.Outlined.History, "History", onSeeAllTransactions, weight)
                }
            }
            item(key = "budget") {
                BudgetPlannerCard(onClick = onOpenBudget, modifier = Modifier.padding(horizontal = 20.dp, vertical = 8.dp))
            }
            if (summary.accounts.size > 1) {
                item(key = "accounts") {
                    Column(Modifier.padding(vertical = 8.dp), verticalArrangement = Arrangement.spacedBy(8.dp)) {
                        SectionTitle("Wallets", Modifier.padding(horizontal = 20.dp))
                        AccountsRow(
                            accounts = summary.accounts,
                            hideBalances = summary.hideBalances,
                            modifier = Modifier.padding(start = 20.dp),
                        )
                    }
                }
            }
            item(key = "recent-title") {
                SectionTitle(
                    "Recent activity",
                    Modifier.padding(start = 20.dp, end = 8.dp, top = 12.dp),
                ) { TextButton(onClick = onSeeAllTransactions) { Text("See all") } }
            }
            if (summary.recentTransactions.isEmpty()) {
                item(key = "empty") {
                    EmptyState(
                        icon = Icons.AutoMirrored.Outlined.ReceiptLong,
                        title = "No activity yet",
                        message = "Money you send and receive will show up here.",
                    )
                }
            } else {
                recentTransactionItems(
                    transactions = summary.recentTransactions,
                    hideAmounts = summary.hideBalances,
                    onTransactionClick = onTransactionClick,
                )
            }
        }
    }

    if (showReceive && summary.accounts.isNotEmpty()) {
        ReceiveSheet(holderName = summary.holderName, accounts = summary.accounts, onDismiss = { showReceive = false })
    }
}

private fun greeting(): String = when (LocalTime.now().hour) {
    in 5..11 -> "Good morning,"
    in 12..16 -> "Good afternoon,"
    else -> "Good evening,"
}
