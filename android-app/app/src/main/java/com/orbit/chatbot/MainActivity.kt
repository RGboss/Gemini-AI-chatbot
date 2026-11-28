package com.orbit.chatbot

import android.os.Bundle
import androidx.activity.ComponentActivity
import androidx.activity.compose.setContent
import androidx.activity.enableEdgeToEdge
import androidx.activity.viewModels
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.material3.Surface
import androidx.compose.ui.Modifier
import androidx.compose.ui.graphics.Color
import com.orbit.chatbot.network.EmbeddedHttpServer
import com.orbit.chatbot.ui.theme.OrbitTheme

class MainActivity : ComponentActivity() {

    private val viewModel: ChatViewModel by viewModels()
    private var embeddedServer: EmbeddedHttpServer? = null

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        enableEdgeToEdge()

        // Start embedded HTTP server (serving frontend SPA assets + API locally)
        embeddedServer = EmbeddedHttpServer(this, port = 8080).apply {
            start()
        }

        setContent {
            OrbitTheme {
                Surface(
                    modifier = Modifier.fillMaxSize(),
                    color = Color(0xFF0A0D14)
                ) {
                    OrbitApp(viewModel = viewModel)
                }
            }
        }
    }

    override fun onDestroy() {
        super.onDestroy()
        embeddedServer?.stop()
    }
}
