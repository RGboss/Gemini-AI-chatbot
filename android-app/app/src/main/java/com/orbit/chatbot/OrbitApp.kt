package com.orbit.chatbot

import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.padding
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.filled.AutoAwesome
import androidx.compose.material.icons.filled.Hub
import androidx.compose.material.icons.filled.Language
import androidx.compose.material.icons.filled.Settings
import androidx.compose.material3.*
import androidx.compose.runtime.*
import androidx.compose.ui.Modifier
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.graphics.vector.ImageVector
import androidx.compose.ui.unit.dp
import com.orbit.chatbot.ui.screens.ChatScreen
import com.orbit.chatbot.ui.screens.SettingsScreen
import com.orbit.chatbot.ui.screens.WebPortalScreen
import com.orbit.chatbot.ui.screens.WorkerNodeScreen

enum class AppTab(val title: String, val icon: ImageVector) {
    CHAT("Chat", Icons.Default.AutoAwesome),
    PORTAL("Portal", Icons.Default.Language),
    NODE("Worker", Icons.Default.Hub),
    SETTINGS("Settings", Icons.Default.Settings)
}

@Composable
fun OrbitApp(
    viewModel: ChatViewModel
) {
    var selectedTab by remember { mutableStateOf(AppTab.CHAT) }

    Scaffold(
        bottomBar = {
            NavigationBar(
                containerColor = Color(0xFF0F172A),
                tonalElevation = 8.dp
            ) {
                AppTab.values().forEach { tab ->
                    NavigationBarItem(
                        selected = selectedTab == tab,
                        onClick = { selectedTab = tab },
                        icon = { Icon(tab.icon, contentDescription = tab.title) },
                        label = { Text(tab.title) },
                        colors = NavigationBarItemDefaults.colors(
                            selectedIconColor = Color(0xFF00D2FF),
                            selectedTextColor = Color(0xFF00D2FF),
                            unselectedIconColor = Color(0xFF64748B),
                            unselectedTextColor = Color(0xFF64748B),
                            indicatorColor = Color(0xFF1E2638)
                        )
                    )
                }
            }
        },
        containerColor = Color(0xFF0A0D14)
    ) { innerPadding ->
        when (selectedTab) {
            AppTab.CHAT -> ChatScreen(
                viewModel = viewModel,
                modifier = Modifier.padding(innerPadding)
            )
            AppTab.PORTAL -> WebPortalScreen(
                modifier = Modifier.padding(innerPadding)
            )
            AppTab.NODE -> WorkerNodeScreen(
                viewModel = viewModel,
                modifier = Modifier.padding(innerPadding)
            )
            AppTab.SETTINGS -> SettingsScreen(
                modifier = Modifier.padding(innerPadding)
            )
        }
    }
}
