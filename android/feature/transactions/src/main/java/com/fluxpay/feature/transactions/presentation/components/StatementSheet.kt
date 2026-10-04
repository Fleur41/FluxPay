package com.fluxpay.feature.transactions.presentation.components

import android.content.ActivityNotFoundException
import android.content.Context
import android.content.Intent
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.ExperimentalLayoutApi
import androidx.compose.foundation.layout.FlowRow
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.navigationBarsPadding
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.width
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.automirrored.outlined.OpenInNew
import androidx.compose.material.icons.outlined.CheckCircle
import androidx.compose.material.icons.outlined.Share
import androidx.compose.material3.ExperimentalMaterial3Api
import androidx.compose.material3.FilterChip
import androidx.compose.material3.Icon
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.ModalBottomSheet
import androidx.compose.material3.OutlinedButton
import androidx.compose.material3.SegmentedButton
import androidx.compose.material3.SegmentedButtonDefaults
import androidx.compose.material3.SingleChoiceSegmentedButtonRow
import androidx.compose.material3.Text
import androidx.compose.material3.rememberModalBottomSheetState
import androidx.compose.runtime.Composable
import androidx.compose.runtime.getValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.unit.dp
import androidx.core.content.FileProvider
import androidx.hilt.navigation.compose.hiltViewModel
import androidx.lifecycle.compose.collectAsStateWithLifecycle
import com.fluxpay.core.domain.model.DownloadedStatement
import com.fluxpay.core.domain.model.StatementFormat
import com.fluxpay.core.ui.components.FluxPrimaryButton
import com.fluxpay.feature.transactions.presentation.viewmodel.StatementViewModel
import java.time.format.DateTimeFormatter
import java.time.format.FormatStyle

@OptIn(ExperimentalMaterial3Api::class, ExperimentalLayoutApi::class)
@Composable
fun StatementSheet(
    onDismiss: () -> Unit,
    viewModel: StatementViewModel = hiltViewModel(),
) {
    val state by viewModel.state.collectAsStateWithLifecycle()
    val context = LocalContext.current
    val dates = DateTimeFormatter.ofLocalizedDate(FormatStyle.MEDIUM)

    ModalBottomSheet(
        onDismissRequest = {
            viewModel.reset()
            onDismiss()
        },
        sheetState = rememberModalBottomSheetState(skipPartiallyExpanded = true),
    ) {
        Column(
            Modifier
                .fillMaxWidth()
                .padding(horizontal = 24.dp)
                .navigationBarsPadding()
                .padding(bottom = 24.dp),
            verticalArrangement = Arrangement.spacedBy(16.dp),
        ) {
            Text("Download statement", style = MaterialTheme.typography.titleLarge)

            Column(verticalArrangement = Arrangement.spacedBy(8.dp)) {
                Text("Period", style = MaterialTheme.typography.labelLarge)
                FlowRow(horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                    state.ranges.forEach { range ->
                        FilterChip(
                            selected = state.range == range,
                            onClick = { viewModel.onRangeChange(range) },
                            label = { Text(range.label) },
                        )
                    }
                }
                Text(
                    "${dates.format(state.period.from)} – ${dates.format(state.period.to)}",
                    style = MaterialTheme.typography.bodySmall,
                    color = MaterialTheme.colorScheme.onSurfaceVariant,
                )
            }

            Column(verticalArrangement = Arrangement.spacedBy(8.dp)) {
                Text("Format", style = MaterialTheme.typography.labelLarge)
                SingleChoiceSegmentedButtonRow(Modifier.fillMaxWidth()) {
                    val formats = StatementFormat.entries
                    formats.forEachIndexed { index, format ->
                        SegmentedButton(
                            selected = state.format == format,
                            onClick = { viewModel.onFormatChange(format) },
                            shape = SegmentedButtonDefaults.itemShape(index, formats.size),
                        ) { Text(if (format == StatementFormat.PDF) "PDF" else "CSV (spreadsheet)") }
                    }
                }
            }

            state.error?.let { Text(it, color = MaterialTheme.colorScheme.error, style = MaterialTheme.typography.bodyMedium) }

            val downloaded = state.downloaded
            if (downloaded == null) {
                FluxPrimaryButton(text = "Download", onClick = viewModel::download, loading = state.isDownloading)
            } else {
                Row(verticalAlignment = Alignment.CenterVertically) {
                    Icon(Icons.Outlined.CheckCircle, contentDescription = null, tint = MaterialTheme.colorScheme.primary)
                    Spacer(Modifier.width(8.dp))
                    Text(downloaded.fileName, style = MaterialTheme.typography.bodyMedium)
                }
                Row(horizontalArrangement = Arrangement.spacedBy(12.dp)) {
                    OutlinedButton(
                        onClick = { openStatement(context, downloaded)?.let(viewModel::onOpenFailed) },
                        modifier = Modifier.weight(1f),
                    ) {
                        Icon(Icons.AutoMirrored.Outlined.OpenInNew, contentDescription = null)
                        Spacer(Modifier.width(8.dp))
                        Text("Open")
                    }
                    OutlinedButton(onClick = { shareStatement(context, downloaded) }, modifier = Modifier.weight(1f)) {
                        Icon(Icons.Outlined.Share, contentDescription = null)
                        Spacer(Modifier.width(8.dp))
                        Text("Share or save")
                    }
                }
            }
            Spacer(Modifier.height(4.dp))
        }
    }
}

/** The app's FileProvider (declared in :app with this authority) serves cache/statements/. */
private fun DownloadedStatement.uri(context: Context) =
    FileProvider.getUriForFile(context, "${context.packageName}.fileprovider", file)

/** Returns an error message when no app on this phone can open the file. */
private fun openStatement(context: Context, statement: DownloadedStatement): String? {
    val intent = Intent(Intent.ACTION_VIEW)
        .setDataAndType(statement.uri(context), statement.format.mimeType)
        .addFlags(Intent.FLAG_GRANT_READ_URI_PERMISSION)
    return try {
        context.startActivity(intent)
        null
    } catch (e: ActivityNotFoundException) {
        "No app on this phone can open ${statement.format.extension.uppercase()} files. Use \"Share or save\" instead."
    }
}

private fun shareStatement(context: Context, statement: DownloadedStatement) {
    val send = Intent(Intent.ACTION_SEND)
        .setType(statement.format.mimeType)
        .putExtra(Intent.EXTRA_STREAM, statement.uri(context))
        .putExtra(Intent.EXTRA_SUBJECT, statement.fileName)
        .addFlags(Intent.FLAG_GRANT_READ_URI_PERMISSION)
    context.startActivity(Intent.createChooser(send, "Share statement"))
}
