package com.fluxpay.feature.dashboard.presentation.components

import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.PaddingValues
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.width
import androidx.compose.foundation.lazy.LazyRow
import androidx.compose.foundation.lazy.items
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.automirrored.outlined.KeyboardArrowRight
import androidx.compose.material.icons.outlined.Calculate
import androidx.compose.material.icons.outlined.Storefront
import androidx.compose.material3.Card
import androidx.compose.material3.CardDefaults
import androidx.compose.material3.FilledTonalButton
import androidx.compose.material3.Icon
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.graphics.vector.ImageVector
import androidx.compose.ui.unit.dp
import com.fluxpay.core.common.util.maskAccountNumber
import com.fluxpay.core.domain.model.Account
import com.fluxpay.core.domain.model.BusinessBalance
import com.fluxpay.core.domain.model.MyPayslip
import com.fluxpay.core.ui.components.MoneyText

/** Icon above label, so three actions fit side by side on a phone. */
@Composable
fun QuickAction(icon: ImageVector, label: String, onClick: () -> Unit, modifier: Modifier = Modifier) {
    FilledTonalButton(
        onClick = onClick,
        modifier = modifier.height(72.dp),
        shape = MaterialTheme.shapes.medium,
        contentPadding = PaddingValues(horizontal = 4.dp, vertical = 8.dp),
    ) {
        Column(horizontalAlignment = Alignment.CenterHorizontally) {
            Icon(icon, contentDescription = null)
            Spacer(Modifier.height(4.dp))
            Text(label, style = MaterialTheme.typography.labelLarge)
        }
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

/** Entry point to the budget planner (feature:budget). */
@Composable
fun BudgetPlannerCard(onClick: () -> Unit, modifier: Modifier = Modifier) {
    Card(onClick = onClick, modifier = modifier.fillMaxWidth()) {
        Row(Modifier.padding(16.dp), verticalAlignment = Alignment.CenterVertically) {
            Icon(Icons.Outlined.Calculate, contentDescription = null, tint = MaterialTheme.colorScheme.primary)
            Spacer(Modifier.width(16.dp))
            Column(Modifier.weight(1f)) {
                Text("Budget planner", style = MaterialTheme.typography.titleSmall)
                Text(
                    "Plan your month and see what's left",
                    style = MaterialTheme.typography.bodySmall,
                    color = MaterialTheme.colorScheme.onSurfaceVariant,
                )
            }
            Icon(Icons.AutoMirrored.Outlined.KeyboardArrowRight, contentDescription = null)
        }
    }
}


/** A business the user runs: its cashbook balance, next to their personal one. Tapping opens the business. */
@Composable
fun BusinessCashbookCard(item: BusinessBalance, hideBalances: Boolean, onClick: () -> Unit, modifier: Modifier = Modifier) {
    Card(onClick = onClick, modifier = modifier.fillMaxWidth()) {
        Row(Modifier.padding(16.dp), verticalAlignment = Alignment.CenterVertically) {
            Icon(Icons.Outlined.Storefront, contentDescription = null, tint = MaterialTheme.colorScheme.primary)
            Spacer(Modifier.width(16.dp))
            Column(Modifier.weight(1f)) {
                Text(item.business.name, style = MaterialTheme.typography.titleSmall)
                Text(
                    listOfNotNull(
                        "Business account",
                        item.cashbook?.accountNumber?.maskAccountNumber(),
                        "you are ${item.business.roleLabel.lowercase()}",
                    ).joinToString(" · "),
                    style = MaterialTheme.typography.bodySmall,
                    color = MaterialTheme.colorScheme.onSurfaceVariant,
                )
            }
            val cashbook = item.cashbook
            if (cashbook != null) {
                MoneyText(
                    amount = cashbook.balance,
                    currency = cashbook.currency,
                    hidden = hideBalances,
                    style = MaterialTheme.typography.titleMedium,
                )
            } else {
                Text("Unavailable", style = MaterialTheme.typography.bodySmall, color = MaterialTheme.colorScheme.onSurfaceVariant)
            }
            Icon(Icons.AutoMirrored.Outlined.KeyboardArrowRight, contentDescription = null)
        }
    }
}

/** One payment the user received as a worker (salary, allowance, bonus...). */
@Composable
fun MyPayRow(pay: MyPayslip, hideBalances: Boolean, modifier: Modifier = Modifier) {
    Row(modifier.fillMaxWidth().padding(vertical = 8.dp), verticalAlignment = Alignment.CenterVertically) {
        Column(Modifier.weight(1f)) {
            Text(pay.title, style = MaterialTheme.typography.titleSmall)
            Text(
                "${pay.business} · ${pay.payDate}" + if (pay.isReversed) " · ${pay.statusLabel}" else "",
                style = MaterialTheme.typography.bodySmall,
                color = if (pay.isReversed) MaterialTheme.colorScheme.error else MaterialTheme.colorScheme.onSurfaceVariant,
            )
        }
        MoneyText(amount = pay.amount, currency = pay.currency, hidden = hideBalances, style = MaterialTheme.typography.titleSmall)
    }
}


/** For people not yet paid by a business: the way in to join their employer (invitation code or QR). */
@Composable
fun JoinEmployerCard(onClick: () -> Unit, modifier: Modifier = Modifier) {
    Card(onClick = onClick, modifier = modifier.fillMaxWidth()) {
        Row(Modifier.padding(16.dp), verticalAlignment = Alignment.CenterVertically) {
            Icon(Icons.Outlined.Storefront, contentDescription = null, tint = MaterialTheme.colorScheme.primary)
            Spacer(Modifier.width(16.dp))
            Column(Modifier.weight(1f)) {
                Text("Do you work for a business?", style = MaterialTheme.typography.titleSmall)
                Text(
                    "Join your employer with your invitation code or their QR code, and get paid here",
                    style = MaterialTheme.typography.bodySmall,
                    color = MaterialTheme.colorScheme.onSurfaceVariant,
                )
            }
            Icon(Icons.AutoMirrored.Outlined.KeyboardArrowRight, contentDescription = null)
        }
    }
}
