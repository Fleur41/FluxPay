package com.fluxpay.feature.transfer.navigation

import androidx.navigation.NavGraphBuilder
import androidx.navigation.compose.composable
import com.fluxpay.feature.transfer.presentation.TransferScreen

object TransferRoutes {
    const val TRANSFER = "transfer"
}

fun NavGraphBuilder.transferScreen(
    onDone: () -> Unit,
    onViewTransaction: (transactionId: String) -> Unit,
) {
    composable(TransferRoutes.TRANSFER) {
        TransferScreen(onDone = onDone, onViewTransaction = onViewTransaction)
    }
}
