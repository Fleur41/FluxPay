package com.fluxpay.feature.transfer.presentation.components

import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.width
import androidx.compose.material3.Card
import androidx.compose.material3.DropdownMenuItem
import androidx.compose.material3.ExperimentalMaterial3Api
import androidx.compose.material3.ExposedDropdownMenuBox
import androidx.compose.material3.ExposedDropdownMenuDefaults
import androidx.compose.material3.HorizontalDivider
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.MenuAnchorType
import androidx.compose.material3.OutlinedTextField
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.unit.dp
import com.fluxpay.core.common.util.MoneyFormatter
import com.fluxpay.core.common.util.maskAccountNumber
import com.fluxpay.core.domain.model.Account
import com.fluxpay.core.ui.components.Avatar

@OptIn(ExperimentalMaterial3Api::class)
@Composable
fun SourceAccountPicker(
    accounts: List<Account>,
    selected: Account?,
    hideBalances: Boolean,
    onSelect: (String) -> Unit,
    error: String?,
) {
    var expanded by remember { mutableStateOf(false) }
    fun Account.describe() = "$name · ${accountNumber.maskAccountNumber()}"
    fun Account.available() =
        "Available: " + if (hideBalances) MoneyFormatter.MASK else MoneyFormatter.format(balance, currency)

    ExposedDropdownMenuBox(expanded = expanded, onExpandedChange = { expanded = it && accounts.size > 1 }) {
        OutlinedTextField(
            value = selected?.describe() ?: "No wallet",
            onValueChange = {},
            readOnly = true,
            label = { Text("From") },
            supportingText = { Text(error ?: selected?.available().orEmpty()) },
            isError = error != null,
            trailingIcon = { if (accounts.size > 1) ExposedDropdownMenuDefaults.TrailingIcon(expanded) },
            shape = MaterialTheme.shapes.medium,
            modifier = Modifier.fillMaxWidth().menuAnchor(MenuAnchorType.PrimaryNotEditable),
        )
        ExposedDropdownMenu(expanded = expanded, onDismissRequest = { expanded = false }) {
            accounts.forEach { account ->
                DropdownMenuItem(
                    text = {
                        Column {
                            Text(account.describe())
                            Text(account.available(), style = MaterialTheme.typography.bodySmall)
                        }
                    },
                    onClick = {
                        onSelect(account.id)
                        expanded = false
                    },
                )
            }
        }
    }
}

@Composable
fun SummaryRow(label: String, value: String) {
    Row(Modifier.fillMaxWidth().padding(vertical = 10.dp), horizontalArrangement = Arrangement.SpaceBetween) {
        Text(label, color = MaterialTheme.colorScheme.onSurfaceVariant, style = MaterialTheme.typography.bodyMedium)
        Text(value, style = MaterialTheme.typography.bodyMedium)
    }
}

@Composable
fun RecipientCard(name: String, accountNumber: String, rows: List<Pair<String, String>>) {
    Card(Modifier.fillMaxWidth()) {
        Column(Modifier.padding(16.dp)) {
            Row(verticalAlignment = Alignment.CenterVertically) {
                Avatar(name)
                Spacer(Modifier.width(12.dp))
                Column {
                    Text(name, style = MaterialTheme.typography.titleMedium)
                    Text(
                        accountNumber,
                        style = MaterialTheme.typography.bodySmall,
                        color = MaterialTheme.colorScheme.onSurfaceVariant,
                    )
                }
            }
            HorizontalDivider(Modifier.padding(vertical = 8.dp))
            rows.forEach { (label, value) -> SummaryRow(label, value) }
        }
    }
}
