package com.fluxpay.feature.transactions.presentation

import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.PaddingValues
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.automirrored.outlined.ReceiptLong
import androidx.compose.material.icons.outlined.Close
import androidx.compose.material.icons.outlined.Search
import androidx.compose.material.icons.outlined.SearchOff
import androidx.compose.material3.ExperimentalMaterial3Api
import androidx.compose.material3.FilterChip
import androidx.compose.material3.Icon
import androidx.compose.material3.IconButton
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.OutlinedTextField
import androidx.compose.material3.Scaffold
import androidx.compose.material3.Text
import androidx.compose.material3.TopAppBar
import androidx.compose.material3.pulltorefresh.PullToRefreshBox
import androidx.compose.runtime.Composable
import androidx.compose.runtime.getValue
import androidx.compose.ui.Modifier
import androidx.compose.ui.unit.dp
import androidx.hilt.navigation.compose.hiltViewModel
import androidx.lifecycle.compose.collectAsStateWithLifecycle
import com.fluxpay.core.domain.model.Transaction
import com.fluxpay.core.ui.adapter.transactionItems
import com.fluxpay.core.ui.components.EmptyState
import com.fluxpay.core.ui.components.ErrorBanner
import com.fluxpay.feature.transactions.domain.model.TypeFilter
import com.fluxpay.feature.transactions.presentation.viewmodel.TransactionsViewModel

@OptIn(ExperimentalMaterial3Api::class)
@Composable
fun TransactionsScreen(
    onTransactionClick: (Transaction) -> Unit,
    viewModel: TransactionsViewModel = hiltViewModel(),
) {
    val state by viewModel.state.collectAsStateWithLifecycle()

    Scaffold(topBar = { TopAppBar(title = { Text("Transactions") }) }) { padding ->
        Column(Modifier.padding(padding).fillMaxSize()) {
            OutlinedTextField(
                value = state.query,
                onValueChange = viewModel::onQueryChange,
                placeholder = { Text("Search name, note or reference") },
                leadingIcon = { Icon(Icons.Outlined.Search, contentDescription = null) },
                trailingIcon = {
                    if (state.query.isNotEmpty()) {
                        IconButton(onClick = { viewModel.onQueryChange("") }) {
                            Icon(Icons.Outlined.Close, contentDescription = "Clear search")
                        }
                    }
                },
                singleLine = true,
                shape = MaterialTheme.shapes.medium,
                modifier = Modifier.padding(horizontal = 16.dp).fillMaxWidth(),
            )
            Row(
                modifier = Modifier.padding(horizontal = 16.dp, vertical = 8.dp),
                horizontalArrangement = Arrangement.spacedBy(8.dp),
            ) {
                TypeFilter.entries.forEach { filter ->
                    FilterChip(
                        selected = state.typeFilter == filter,
                        onClick = { viewModel.onTypeFilterChange(filter) },
                        label = { Text(filter.label) },
                    )
                }
            }
            state.error?.let { error ->
                ErrorBanner(
                    message = error.message,
                    offline = error.isNetworkFailure,
                    onRetry = viewModel::refresh,
                    modifier = Modifier.padding(horizontal = 16.dp, vertical = 4.dp),
                )
            }
            PullToRefreshBox(
                isRefreshing = state.isRefreshing,
                onRefresh = viewModel::refresh,
                modifier = Modifier.fillMaxSize(),
            ) {
                LazyColumn(Modifier.fillMaxSize(), contentPadding = PaddingValues(bottom = 24.dp)) {
                    if (state.isLoaded && state.items.isEmpty()) {
                        item(key = "empty") {
                            if (state.isFiltering) {
                                EmptyState(Icons.Outlined.SearchOff, "No matches", "Try a different search or filter.")
                            } else {
                                EmptyState(
                                    Icons.AutoMirrored.Outlined.ReceiptLong,
                                    "No transactions yet",
                                    "Your history will appear here.",
                                )
                            }
                        }
                    }
                    transactionItems(
                        items = state.items,
                        hideAmounts = state.hideAmounts,
                        onTransactionClick = onTransactionClick,
                    )
                }
            }
        }
    }
}
