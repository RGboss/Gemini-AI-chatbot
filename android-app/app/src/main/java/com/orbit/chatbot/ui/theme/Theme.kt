package com.orbit.chatbot.ui.theme

import android.app.Activity
import androidx.compose.foundation.isSystemInDarkTheme
import androidx.compose.material3.*
import androidx.compose.runtime.Composable
import androidx.compose.runtime.SideEffect
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.graphics.toArgb
import androidx.compose.ui.platform.LocalView
import androidx.core.view.WindowCompat

private val OrbitDarkColorScheme = darkColorScheme(
    primary = Color(0xFF00D2FF),
    onPrimary = Color(0xFF0A0D14),
    primaryContainer = Color(0xFF0284C7),
    onPrimaryContainer = Color.White,
    secondary = Color(0xFF818CF8),
    onSecondary = Color(0xFF0A0D14),
    secondaryContainer = Color(0xFF312E81),
    onSecondaryContainer = Color.White,
    background = Color(0xFF0A0D14),
    onBackground = Color(0xFFF1F5F9),
    surface = Color(0xFF111625),
    onSurface = Color(0xFFF1F5F9),
    surfaceVariant = Color(0xFF1E2638),
    onSurfaceVariant = Color(0xFF94A3B8),
    error = Color(0xFFEF4444),
    onError = Color.White
)

@Composable
fun OrbitTheme(
    darkTheme: Boolean = true, // Default to sleek enterprise dark
    content: @Composable () -> Unit
) {
    val colorScheme = OrbitDarkColorScheme
    val view = LocalView.current
    if (!view.isInEditMode) {
        SideEffect {
            val window = (view.context as Activity).window
            window.statusBarColor = Color(0xFF0A0D14).toArgb()
            window.navigationBarColor = Color(0xFF0A0D14).toArgb()
            WindowCompat.getInsetsController(window, view).isAppearanceLightStatusBars = false
            WindowCompat.getInsetsController(window, view).isAppearanceLightNavigationBars = false
        }
    }

    MaterialTheme(
        colorScheme = colorScheme,
        content = content
    )
}
