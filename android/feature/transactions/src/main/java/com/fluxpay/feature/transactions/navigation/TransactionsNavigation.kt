package com.fluxpay.feature.transactions.navigation

import androidx.hilt.navigation.compose.hiltViewModel
import androidx.navigation.NavController
import androidx.navigation.NavGraphBuilder
import androidx.navigation.NavType
import androidx.navigation.compose.composable
import androidx.navigation.navArgument
import androidx.navigation.navDeepLink
import com.fluxpay.core.common.util.Constants
import com.fluxpay.feature.transactions.presentation.TransactionDetailScreen
import com.fluxpay.feature.transactions.presentation.TransactionsScreen
import com.fluxpay.feature.transactions.presentation.viewmodel.TransactionDetailViewModel

object TransactionsRoutes {
    const val LIST = "transactions"
    const val ARG_ID = "transactionId"
    const val DETAIL = "transactions/{$ARG_ID}"

    /** e.g. a push notification or email linking to fluxpay://transaction/<uuid> */
    val DETAIL_DEEP_LINKS = listOf(
        "${Constants.DEEP_LINK_SCHEME}://transaction/{$ARG_ID}",
        "https://${Constants.DEEP_LINK_HOST}/transaction/{$ARG_ID}",
    )

    fun detail(id: String) = "transactions/$id"
}

fun NavController.navigateToTransaction(id: String) = navigate(TransactionsRoutes.detail(id)) {
    launchSingleTop = true
}

fun NavGraphBuilder.transactionsScreens(navController: NavController) {
    composable(TransactionsRoutes.LIST) {
        TransactionsScreen(onTransactionClick = { navController.navigateToTransaction(it.id) })
    }
    composable(
        route = TransactionsRoutes.DETAIL,
        arguments = listOf(navArgument(TransactionsRoutes.ARG_ID) { type = NavType.StringType }),
        deepLinks = TransactionsRoutes.DETAIL_DEEP_LINKS.map { pattern -> navDeepLink { uriPattern = pattern } },
    ) { entry ->
        val id = entry.arguments?.getString(TransactionsRoutes.ARG_ID).orEmpty()
        val viewModel = hiltViewModel<TransactionDetailViewModel, TransactionDetailViewModel.Factory>(
            creationCallback = { factory -> factory.create(id) },
        )
        TransactionDetailScreen(viewModel = viewModel, onBack = navController::popBackStack)
    }
}
