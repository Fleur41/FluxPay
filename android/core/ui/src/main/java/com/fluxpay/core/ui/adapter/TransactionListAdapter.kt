package com.fluxpay.core.ui.adapter

import androidx.compose.foundation.ExperimentalFoundationApi
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.lazy.LazyListScope
import androidx.compose.foundation.lazy.items
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Surface
import androidx.compose.material3.Text
import androidx.compose.ui.Modifier
import androidx.compose.ui.unit.dp
import com.fluxpay.core.common.util.DateFormatter
import com.fluxpay.core.domain.model.Transaction
import com.fluxpay.core.ui.components.TransactionRow
import java.time.LocalDate
import java.time.ZoneId

/** UI rows for a LazyColumn: a day header followed by that day's transactions. */
sealed interface TransactionListItem {
    val key: String

    data class Header(val day: LocalDate, val label: String) : TransactionListItem {
        override val key: String = "header-$day"
    }

    data class Row(val transaction: Transaction) : TransactionListItem {
        override val key: String = transaction.id
    }
}

/**
 * Adapter pattern for Compose lists — the Compose equivalent of a RecyclerView.Adapter.
 * Converts domain [Transaction]s into typed list items and binds each type to a composable,
 * with stable keys and content types so LazyColumn can reuse compositions efficiently.
 */
object TransactionListAdapter {

    fun adapt(
        transactions: List<Transaction>,
        zone: ZoneId = ZoneId.systemDefault(),
        today: LocalDate = LocalDate.now(zone),
    ): List<TransactionListItem> = buildList {
        transactions
            .groupBy { it.createdAt.atZone(zone).toLocalDate() }
            .toSortedMap(compareByDescending { it })
            .forEach { (day, dayTransactions) ->
                add(TransactionListItem.Header(day, DateFormatter.dayHeader(day, today)))
                dayTransactions.sortedByDescending { it.createdAt }.forEach { add(TransactionListItem.Row(it)) }
            }
    }
}

@OptIn(ExperimentalFoundationApi::class)
fun LazyListScope.transactionItems(
    items: List<TransactionListItem>,
    hideAmounts: Boolean,
    onTransactionClick: (Transaction) -> Unit,
    stickyHeaders: Boolean = true,
) {
    items.forEach { item ->
        when (item) {
            is TransactionListItem.Header -> {
                val header: @androidx.compose.runtime.Composable () -> Unit = {
                    Surface(color = MaterialTheme.colorScheme.background, modifier = Modifier.fillMaxWidth()) {
                        Text(
                            item.label,
                            style = MaterialTheme.typography.labelLarge,
                            color = MaterialTheme.colorScheme.onSurfaceVariant,
                            modifier = Modifier.padding(horizontal = 16.dp, vertical = 8.dp),
                        )
                    }
                }
                if (stickyHeaders) {
                    stickyHeader(key = item.key, contentType = "header") { header() }
                } else {
                    item(key = item.key, contentType = "header") { header() }
                }
            }
            is TransactionListItem.Row -> item(key = item.key, contentType = "transaction") {
                TransactionRow(
                    transaction = item.transaction,
                    hideAmounts = hideAmounts,
                    onClick = { onTransactionClick(item.transaction) },
                )
            }
        }
    }
}

/** Flat variant for short lists such as "recent transactions" on the dashboard. */
fun LazyListScope.recentTransactionItems(
    transactions: List<Transaction>,
    hideAmounts: Boolean,
    onTransactionClick: (Transaction) -> Unit,
) {
    items(transactions, key = { it.id }, contentType = { "transaction" }) { transaction ->
        TransactionRow(transaction, hideAmounts, onClick = { onTransactionClick(transaction) })
    }
}
