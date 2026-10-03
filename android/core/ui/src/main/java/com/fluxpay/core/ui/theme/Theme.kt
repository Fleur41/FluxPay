package com.fluxpay.core.ui.theme

import androidx.compose.foundation.isSystemInDarkTheme
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Shapes
import androidx.compose.material3.Typography
import androidx.compose.material3.darkColorScheme
import androidx.compose.material3.lightColorScheme
import androidx.compose.runtime.Composable
import androidx.compose.runtime.Immutable
import androidx.compose.runtime.staticCompositionLocalOf
import androidx.compose.ui.graphics.Brush
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.text.TextStyle
import androidx.compose.ui.text.font.FontFamily
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import com.fluxpay.core.domain.model.ThemeMode

// FluxPay brand: an electric violet → teal "flux" gradient on calm neutrals.
private val Violet = Color(0xFF5B3FE4)
private val VioletLight = Color(0xFFB9A8FF)
private val VioletContainer = Color(0xFFE6DEFF)
private val VioletContainerDark = Color(0xFF3A23B0)
private val Teal = Color(0xFF00A88F)
private val TealLight = Color(0xFF4FDBC2)
private val Ink = Color(0xFF14121F)
private val InkSurface = Color(0xFF1D1A2C)
private val Mist = Color(0xFFF7F6FB)
private val Coral = Color(0xFFD9364F)
private val CoralLight = Color(0xFFFF8A9A)

private val LightColors = lightColorScheme(
    primary = Violet,
    onPrimary = Color.White,
    primaryContainer = VioletContainer,
    onPrimaryContainer = Color(0xFF1B0B66),
    secondary = Teal,
    onSecondary = Color.White,
    secondaryContainer = Color(0xFFC9F4EA),
    onSecondaryContainer = Color(0xFF00382F),
    background = Mist,
    onBackground = Ink,
    surface = Color.White,
    onSurface = Ink,
    surfaceVariant = Color(0xFFECE9F4),
    onSurfaceVariant = Color(0xFF5C5870),
    surfaceContainer = Color(0xFFF1EFF8),
    outline = Color(0xFFCAC5DA),
    error = Coral,
)

private val DarkColors = darkColorScheme(
    primary = VioletLight,
    onPrimary = Color(0xFF240E8C),
    primaryContainer = VioletContainerDark,
    onPrimaryContainer = VioletContainer,
    secondary = TealLight,
    onSecondary = Color(0xFF003730),
    secondaryContainer = Color(0xFF00514A),
    onSecondaryContainer = Color(0xFFC9F4EA),
    background = Ink,
    onBackground = Color(0xFFE7E4F2),
    surface = InkSurface,
    onSurface = Color(0xFFE7E4F2),
    surfaceVariant = Color(0xFF2A2640),
    onSurfaceVariant = Color(0xFFB4AFC9),
    surfaceContainer = Color(0xFF221F33),
    outline = Color(0xFF4A4562),
    error = CoralLight,
)

/** Colors Material 3 doesn't model: money in/out and the brand gradient. */
@Immutable
data class FluxColors(
    val credit: Color,
    val debit: Color,
    val heroGradient: Brush,
)

private val LightFlux = FluxColors(
    credit = Color(0xFF0A8A5F),
    debit = Coral,
    heroGradient = Brush.linearGradient(listOf(Violet, Color(0xFF3B2BB8), Teal)),
)

private val DarkFlux = FluxColors(
    credit = Color(0xFF5BE0A8),
    debit = CoralLight,
    heroGradient = Brush.linearGradient(listOf(Color(0xFF4A30D6), Color(0xFF2A1E8F), Color(0xFF00806E))),
)

val LocalFluxColors = staticCompositionLocalOf { LightFlux }

private val FluxTypography = Typography().run {
    copy(
        displaySmall = displaySmall.copy(fontWeight = FontWeight.Bold, letterSpacing = (-0.5).sp),
        headlineMedium = headlineMedium.copy(fontWeight = FontWeight.SemiBold, letterSpacing = (-0.25).sp),
        headlineSmall = headlineSmall.copy(fontWeight = FontWeight.SemiBold),
        titleLarge = titleLarge.copy(fontWeight = FontWeight.SemiBold),
        titleMedium = titleMedium.copy(fontWeight = FontWeight.SemiBold),
        labelLarge = labelLarge.copy(fontWeight = FontWeight.SemiBold, letterSpacing = 0.2.sp),
    )
}

/** Tabular figures keep columns of amounts aligned. */
val MoneyTextStyle = TextStyle(fontFamily = FontFamily.Default, fontFeatureSettings = "tnum")

private val FluxShapes = Shapes(
    small = RoundedCornerShape(10.dp),
    medium = RoundedCornerShape(16.dp),
    large = RoundedCornerShape(24.dp),
)

@Composable
fun FluxPayTheme(
    themeMode: ThemeMode = ThemeMode.SYSTEM,
    content: @Composable () -> Unit,
) {
    val dark = when (themeMode) {
        ThemeMode.SYSTEM -> isSystemInDarkTheme()
        ThemeMode.LIGHT -> false
        ThemeMode.DARK -> true
    }
    androidx.compose.runtime.CompositionLocalProvider(LocalFluxColors provides if (dark) DarkFlux else LightFlux) {
        MaterialTheme(
            colorScheme = if (dark) DarkColors else LightColors,
            typography = FluxTypography,
            shapes = FluxShapes,
            content = content,
        )
    }
}

object FluxTheme {
    val colors: FluxColors
        @Composable get() = LocalFluxColors.current
}
