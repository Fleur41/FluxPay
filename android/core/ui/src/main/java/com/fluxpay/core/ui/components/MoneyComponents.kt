package com.fluxpay.core.ui.components

import androidx.compose.foundation.background
import androidx.compose.foundation.clickable
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.layout.width
import androidx.compose.foundation.shape.CircleShape
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.automirrored.outlined.CallMade
import androidx.compose.material.icons.automirrored.outlined.CallReceived
import androidx.compose.material.icons.outlined.CardGiftcard
import androidx.compose.material.icons.outlined.Visibility
import androidx.compose.material.icons.outlined.VisibilityOff
import androidx.compose.material3.Icon
import androidx.compose.material3.IconButton
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.clip
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.semantics.contentDescription
import androidx.compose.ui.semantics.semantics
import androidx.compose.ui.text.TextStyle
import androidx.compose.ui.text.style.TextOverflow
import androidx.compose.ui.unit.dp
import com.fluxpay.core.common.util.DateFormatter
import com.fluxpay.core.common.util.MoneyFormatter
import com.fluxpay.core.common.util.maskAccountNumber
import com.fluxpay.core.domain.model.Transaction
import com.fluxpay.core.domain.model.TransactionCategory
import com.fluxpay.core.ui.theme.FluxTheme
import com.fluxpay.core.ui.theme.MoneyTextStyle
import java.math.BigDecimal

/** Renders an amount, or a mask when the user turned on "hide balances". */
@Composable
fun MoneyText(
    amount: BigDecimal,
    currency: String,
    hidden: Boolean,
    modifier: Modifier = Modifier,
    style: TextStyle = MaterialTheme.typography.bodyLarge,
    color: Color = Color.Unspecified,
    signedCredit: Boolean? = null,
) {
    val text = when {
        hidden -> MoneyFormatter.MASK
        signedCredit != null -> MoneyFormatter.formatSigned(amount, currency, signedCredit)
        else -> MoneyFormatter.format(amount, currency)
    }
    Text(
        text = text,
        modifier = modifier.semantics { if (hidden) contentDescription = "Amount hidden" },
        style = style.merge(MoneyTextStyle),
        color = color,
        maxLines = 1,
    )
}

/** The gradient hero card on the dashboard. */
@Composable
fun BalanceCard(
    title: String,
    amount: BigDecimal,
    currency: String,
    hidden: Boolean,
    onToggleHidden: () -> Unit,
    modifier: Modifier = Modifier,
    footer: String? = null,
) {
    Column(
        modifier = modifier
            .fillMaxWidth()
            .clip(MaterialTheme.shapes.large)
            .background(FluxTheme.colors.heroGradient)
            .padding(24.dp),
    ) {
        Row(verticalAlignment = Alignment.CenterVertically) {
            Text(
                title,
                style = MaterialTheme.typography.labelLarge,
                color = Color.White.copy(alpha = 0.85f),
                modifier = Modifier.weight(1f),
            )
            IconButton(onClick = onToggleHidden) {
                Icon(
                    if (hidden) Icons.Outlined.Visibility else Icons.Outlined.VisibilityOff,
                    contentDescription = if (hidden) "Show balances" else "Hide balances",
                    tint = Color.White,
                )
            }
        }
        MoneyText(
            amount = amount,
            currency = currency,
            hidden = hidden,
            style = MaterialTheme.typography.displaySmall,
            color = Color.White,
        )
        if (footer != null) {
            Spacer(Modifier.height(12.dp))
            Text(footer, style = MaterialTheme.typography.bodyMedium, color = Color.White.copy(alpha = 0.8f))
        }
    }
}

@Composable
fun TransactionRow(
    transaction: Transaction,
    hideAmounts: Boolean,
    onClick: () -> Unit,
    modifier: Modifier = Modifier,
) {
    val accent = if (transaction.isCredit) FluxTheme.colors.credit else FluxTheme.colors.debit
    Row(
        modifier = modifier
            .fillMaxWidth()
            .clickable(onClick = onClick)
            .padding(horizontal = 16.dp, vertical = 12.dp),
        verticalAlignment = Alignment.CenterVertically,
    ) {
        Box(
            modifier = Modifier.size(44.dp).clip(CircleShape).background(accent.copy(alpha = 0.14f)),
            contentAlignment = Alignment.Center,
        ) {
            Icon(
                imageVector = when {
                    transaction.category == TransactionCategory.BONUS -> Icons.Outlined.CardGiftcard
                    transaction.isCredit -> Icons.AutoMirrored.Outlined.CallReceived
                    else -> Icons.AutoMirrored.Outlined.CallMade
                },
                contentDescription = if (transaction.isCredit) "Money in" else "Money out",
                tint = accent,
            )
        }
        Spacer(Modifier.width(14.dp))
        Column(Modifier.weight(1f), verticalArrangement = Arrangement.spacedBy(2.dp)) {
            Text(
                transaction.counterpartyName.ifBlank { transaction.description.ifBlank { "Transaction" } },
                style = MaterialTheme.typography.titleSmall,
                maxLines = 1,
                overflow = TextOverflow.Ellipsis,
            )
            Text(
                listOfNotNull(
                    transaction.description.takeIf { it.isNotBlank() && it != transaction.counterpartyName },
                    transaction.counterpartyAccount.takeIf { it.isNotBlank() }?.maskAccountNumber(),
                    DateFormatter.time(transaction.createdAt),
                ).joinToString(" · "),
                style = MaterialTheme.typography.bodySmall,
                color = MaterialTheme.colorScheme.onSurfaceVariant,
                maxLines = 1,
                overflow = TextOverflow.Ellipsis,
            )
        }
        Spacer(Modifier.width(8.dp))
        MoneyText(
            amount = transaction.amount,
            currency = transaction.currency,
            hidden = hideAmounts,
            signedCredit = transaction.isCredit,
            style = MaterialTheme.typography.titleSmall,
            color = accent,
        )
    }
}
