package com.fluxpay.feature.transfer.navigation

import androidx.navigation.NavGraphBuilder
import androidx.navigation.compose.composable
import com.fluxpay.feature.transfer.presentation.MpesaWithdrawScreen
import com.fluxpay.feature.transfer.presentation.TransferScreen

object TransferRoutes {
    const val TRANSFER = "transfer"
    const val MPESA = "send-to-mpesa"
}

fun NavGraphBuilder.transferScreen(
    onDone: () -> Unit,
    onViewTransaction: (transactionId: String) -> Unit,
    onBack: () -> Unit,
) {
    composable(TransferRoutes.TRANSFER) {
        TransferScreen(onDone = onDone, onViewTransaction = onViewTransaction)
    }
    composable(TransferRoutes.MPESA) {
        MpesaWithdrawScreen(onBack = onBack, onDone = onBack)
    }
}
