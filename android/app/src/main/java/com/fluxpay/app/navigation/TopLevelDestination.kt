package com.fluxpay.app.navigation

import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.automirrored.filled.ReceiptLong
import androidx.compose.material.icons.automirrored.filled.Send
import androidx.compose.material.icons.automirrored.outlined.ReceiptLong
import androidx.compose.material.icons.automirrored.outlined.Send
import androidx.compose.material.icons.filled.Home
import androidx.compose.material.icons.filled.Settings
import androidx.compose.material.icons.filled.Storefront
import androidx.compose.material.icons.outlined.Home
import androidx.compose.material.icons.outlined.Settings
import androidx.compose.material.icons.outlined.Storefront
import androidx.compose.ui.graphics.vector.ImageVector
import com.fluxpay.feature.business.navigation.BusinessRoutes
import com.fluxpay.feature.dashboard.navigation.DashboardRoutes
import com.fluxpay.feature.settings.navigation.SettingsRoutes
import com.fluxpay.feature.transactions.navigation.TransactionsRoutes
import com.fluxpay.feature.transfer.navigation.TransferRoutes

enum class TopLevelDestination(
    val route: String,
    val label: String,
    val selectedIcon: ImageVector,
    val unselectedIcon: ImageVector,
) {
    HOME(DashboardRoutes.DASHBOARD, "Home", Icons.Filled.Home, Icons.Outlined.Home),
    SEND(TransferRoutes.TRANSFER, "Send", Icons.AutoMirrored.Filled.Send, Icons.AutoMirrored.Outlined.Send),
    ACTIVITY(TransactionsRoutes.LIST, "Activity", Icons.AutoMirrored.Filled.ReceiptLong, Icons.AutoMirrored.Outlined.ReceiptLong),
    BUSINESS(BusinessRoutes.HUB, "Business", Icons.Filled.Storefront, Icons.Outlined.Storefront),
    SETTINGS(SettingsRoutes.SETTINGS, "Settings", Icons.Filled.Settings, Icons.Outlined.Settings),
}
