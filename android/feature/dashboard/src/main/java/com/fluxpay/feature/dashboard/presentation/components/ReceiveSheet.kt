package com.fluxpay.feature.dashboard.presentation.components

import android.content.Context
import android.content.Intent
import android.os.Build
import android.widget.Toast
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.navigationBarsPadding
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.width
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.outlined.ContentCopy
import androidx.compose.material.icons.outlined.Share
import androidx.compose.material3.Card
import androidx.compose.material3.ExperimentalMaterial3Api
import androidx.compose.material3.Icon
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.ModalBottomSheet
import androidx.compose.material3.OutlinedButton
import androidx.compose.material3.Text
import androidx.compose.material3.rememberModalBottomSheetState
import androidx.compose.runtime.Composable
import androidx.compose.ui.Modifier
import androidx.compose.ui.platform.LocalClipboardManager
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.text.AnnotatedString
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.dp
import com.fluxpay.core.domain.model.Account

/** What someone needs to pay you: your name and full account number, ready to copy or share. */
@OptIn(ExperimentalMaterial3Api::class)
@Composable
fun ReceiveSheet(holderName: String, accounts: List<Account>, onDismiss: () -> Unit) {
    val clipboard = LocalClipboardManager.current
    val context = LocalContext.current
    val sheetState = rememberModalBottomSheetState(skipPartiallyExpanded = true)

    ModalBottomSheet(onDismissRequest = onDismiss, sheetState = sheetState) {
        Column(
            Modifier.fillMaxWidth().padding(horizontal = 24.dp).navigationBarsPadding().padding(bottom = 24.dp),
            verticalArrangement = Arrangement.spacedBy(16.dp),
        ) {
            Text("Receive money", style = MaterialTheme.typography.titleLarge)
            Text(
                "Share your account number. Anyone on FluxPay can send to it from Send, using this number.",
                style = MaterialTheme.typography.bodyMedium,
                color = MaterialTheme.colorScheme.onSurfaceVariant,
            )
            accounts.forEach { account ->
                Card(Modifier.fillMaxWidth()) {
                    Column(Modifier.padding(16.dp), verticalArrangement = Arrangement.spacedBy(4.dp)) {
                        Text(holderName, style = MaterialTheme.typography.titleMedium)
                        Text(
                            "${account.name} · ${account.currency}",
                            style = MaterialTheme.typography.bodySmall,
                            color = MaterialTheme.colorScheme.onSurfaceVariant,
                        )
                        Text(
                            account.accountNumber.grouped(),
                            style = MaterialTheme.typography.headlineSmall,
                            fontWeight = FontWeight.SemiBold,
                            modifier = Modifier.padding(vertical = 8.dp),
                        )
                        Row(horizontalArrangement = Arrangement.spacedBy(12.dp)) {
                            OutlinedButton(
                                onClick = {
                                    clipboard.setText(AnnotatedString(account.accountNumber))
                                    confirmCopied(context)
                                },
                                modifier = Modifier.weight(1f),
                            ) {
                                Icon(Icons.Outlined.ContentCopy, contentDescription = null)
                                Spacer(Modifier.width(8.dp))
                                Text("Copy")
                            }
                            OutlinedButton(
                                onClick = { shareAccount(context, holderName, account) },
                                modifier = Modifier.weight(1f),
                            ) {
                                Icon(Icons.Outlined.Share, contentDescription = null)
                                Spacer(Modifier.width(8.dp))
                                Text("Share")
                            }
                        }
                    }
                }
            }
        }
    }
}

/** 7646434343 -> "764 643 4343": easier to read out or check. */
internal fun String.grouped(): String =
    if (length == 10 && all(Char::isDigit)) "${substring(0, 3)} ${substring(3, 6)} ${substring(6)}" else this

private fun confirmCopied(context: Context) {
    // Android 13+ shows its own clipboard confirmation; a second one would be noise.
    if (Build.VERSION.SDK_INT < Build.VERSION_CODES.TIRAMISU) {
        Toast.makeText(context, "Account number copied", Toast.LENGTH_SHORT).show()
    }
}

private fun shareAccount(context: Context, holderName: String, account: Account) {
    val message = "Send me money on FluxPay: $holderName, account ${account.accountNumber} (${account.currency})."
    val send = Intent(Intent.ACTION_SEND).setType("text/plain").putExtra(Intent.EXTRA_TEXT, message)
    context.startActivity(Intent.createChooser(send, "Share account number"))
}
