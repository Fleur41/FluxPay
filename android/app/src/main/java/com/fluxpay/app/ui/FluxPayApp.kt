package com.fluxpay.app.ui

import android.net.Uri
import androidx.compose.foundation.layout.WindowInsets
import androidx.compose.foundation.layout.consumeWindowInsets
import androidx.compose.foundation.layout.padding
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.outlined.Timer
import androidx.compose.material3.AlertDialog
import androidx.compose.material3.Icon
import androidx.compose.material3.NavigationBar
import androidx.compose.material3.NavigationBarItem
import androidx.compose.material3.Scaffold
import androidx.compose.material3.SnackbarHost
import androidx.compose.material3.SnackbarHostState
import androidx.compose.material3.Text
import androidx.compose.material3.TextButton
import androidx.compose.runtime.Composable
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.getValue
import androidx.compose.runtime.remember
import androidx.compose.ui.Modifier
import androidx.navigation.NavDestination.Companion.hierarchy
import androidx.navigation.compose.currentBackStackEntryAsState
import androidx.navigation.compose.rememberNavController
import com.fluxpay.app.navigation.FluxPayNavHost
import com.fluxpay.app.navigation.MAIN_GRAPH
import com.fluxpay.app.navigation.TopLevelDestination
import com.fluxpay.app.navigation.navigateToAuthGraph
import com.fluxpay.app.navigation.navigateToMainGraph
import com.fluxpay.app.navigation.navigateToTopLevel
import com.fluxpay.feature.auth.navigation.AuthRoutes

@Composable
fun FluxPayApp(
    isLoggedIn: Boolean,
    pendingDeepLink: String?,
    onDeepLinkConsumed: () -> Unit,
    sessionWarningSeconds: Long?,
    onStaySignedIn: () -> Unit,
    timedOut: Boolean,
    onTimedOutShown: () -> Unit,
) {
    val navController = rememberNavController()
    val backStackEntry by navController.currentBackStackEntryAsState()
    val currentDestination = backStackEntry?.destination
    val snackbarHostState = remember { SnackbarHostState() }

    // Chosen once; afterwards the session effect below moves between the two graphs.
    val startDestination = remember { if (isLoggedIn) MAIN_GRAPH else AuthRoutes.GRAPH }

    // 1) Session changes drive navigation: login → dashboard, logout/expiry → login.
    LaunchedEffect(isLoggedIn) {
        val inAuth = navController.currentDestination?.hierarchy?.any { it.route == AuthRoutes.GRAPH } ?: !isLoggedIn
        when {
            isLoggedIn && inAuth -> navController.navigateToMainGraph()
            !isLoggedIn && !inAuth -> navController.navigateToAuthGraph()
        }
    }

    // 2) Deep links. Transaction links wait until the user is signed in; reset links open right away.
    LaunchedEffect(pendingDeepLink, isLoggedIn) {
        val link = pendingDeepLink ?: return@LaunchedEffect
        val isPublicLink = link.contains("reset-password")
        if (isLoggedIn || isPublicLink) {
            runCatching { navController.navigate(Uri.parse(link)) } // unknown links are ignored
            onDeepLinkConsumed()
        }
    }

    LaunchedEffect(timedOut) {
        if (timedOut) {
            snackbarHostState.showSnackbar("For your security, you were signed out after 5 minutes of inactivity.")
            onTimedOutShown()
        }
    }

    val showBottomBar = TopLevelDestination.entries.any { it.route == currentDestination?.route }

    Scaffold(
        // Each screen handles its own status-bar inset; this Scaffold only reserves the bottom bar.
        contentWindowInsets = WindowInsets(0, 0, 0, 0),
        snackbarHost = { SnackbarHost(snackbarHostState) },
        bottomBar = {
            if (showBottomBar) {
                NavigationBar {
                    TopLevelDestination.entries.forEach { destination ->
                        val selected = currentDestination?.hierarchy?.any { it.route == destination.route } == true
                        NavigationBarItem(
                            selected = selected,
                            onClick = { navController.navigateToTopLevel(destination) },
                            icon = {
                                Icon(
                                    if (selected) destination.selectedIcon else destination.unselectedIcon,
                                    contentDescription = null,
                                )
                            },
                            label = { Text(destination.label) },
                        )
                    }
                }
            }
        },
    ) { padding ->
        FluxPayNavHost(
            navController = navController,
            startDestination = startDestination,
            modifier = Modifier.padding(padding).consumeWindowInsets(padding),
        )
    }

    if (isLoggedIn && sessionWarningSeconds != null) {
        AlertDialog(
            onDismissRequest = onStaySignedIn,
            icon = { Icon(Icons.Outlined.Timer, contentDescription = null) },
            title = { Text("Still there?") },
            text = { Text("For your security you'll be signed out in $sessionWarningSeconds seconds.") },
            confirmButton = { TextButton(onClick = onStaySignedIn) { Text("Stay signed in") } },
        )
    }
}
