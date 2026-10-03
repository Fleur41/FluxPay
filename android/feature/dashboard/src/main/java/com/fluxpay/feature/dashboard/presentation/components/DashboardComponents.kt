package com.fluxpay.feature.dashboard.presentation.components

import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.width
import androidx.compose.foundation.lazy.LazyRow
import androidx.compose.foundation.lazy.items
import androidx.compose.material3.Card
import androidx.compose.material3.CardDefaults
import androidx.compose.material3.FilledTonalButton
import androidx.compose.material3.Icon
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.ui.Modifier
import androidx.compose.ui.graphics.vector.ImageVector
import androidx.compose.ui.unit.dp
import com.fluxpay.core.common.util.maskAccountNumber
import com.fluxpay.core.domain.model.Account
import com.fluxpay.core.ui.components.MoneyText

@Composable
fun QuickAction(icon: ImageVector, label: String, onClick: () -> Unit, modifier: Modifier = Modifier) {
    FilledTonalButton(onClick = onClick, modifier = modifier.height(52.dp), shape = MaterialTheme.shapes.medium) {
        Icon(icon, contentDescription = null)
        Spacer(Modifier.width(8.dp))
        Text(label)
    }
}

@Composable
fun AccountsRow(accounts: List<Account>, hideBalances: Boolean, modifier: Modifier = Modifier) {
    LazyRow(modifier = modifier, horizontalArrangement = Arrangement.spacedBy(12.dp)) {
        items(accounts, key = { it.id }) { account ->
            Card(
                colors = CardDefaults.cardColors(containerColor = MaterialTheme.colorScheme.surface),
                shape = MaterialTheme.shapes.medium,
            ) {
                Column(Modifier.width(200.dp).padding(16.dp), verticalArrangement = Arrangement.spacedBy(4.dp)) {
                    Text(account.name, style = MaterialTheme.typography.labelLarge)
                    MoneyText(
                        amount = account.balance,
                        currency = account.currency,
                        hidden = hideBalances,
                        style = MaterialTheme.typography.titleMedium,
                    )
                    Text(
                        "${account.currency} · ${account.accountNumber.maskAccountNumber()}",
                        style = MaterialTheme.typography.bodySmall,
                        color = MaterialTheme.colorScheme.onSurfaceVariant,
                    )
                }
            }
        }
    }
}

@Composable
fun QuickActionsRow(modifier: Modifier = Modifier, content: @Composable (Modifier) -> Unit) {
    Row(modifier.fillMaxWidth(), horizontalArrangement = Arrangement.spacedBy(12.dp)) {
        content(Modifier.weight(1f))
    }
}
