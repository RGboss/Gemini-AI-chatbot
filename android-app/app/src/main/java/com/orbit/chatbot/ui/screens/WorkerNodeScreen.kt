package com.orbit.chatbot.ui.screens

import androidx.compose.foundation.background
import androidx.compose.foundation.border
import androidx.compose.foundation.layout.*
import androidx.compose.foundation.shape.CircleShape
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.filled.CheckCircle
import androidx.compose.material.icons.filled.Error
import androidx.compose.material.icons.filled.Refresh
import androidx.compose.material.icons.filled.Router
import androidx.compose.material3.*
import androidx.compose.runtime.*
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.clip
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.text.font.FontFamily
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import com.orbit.chatbot.ChatViewModel
import java.text.SimpleDateFormat
import java.util.Date
import java.util.Locale

@OptIn(ExperimentalMaterial3Api::class)
@Composable
fun WorkerNodeScreen(
    viewModel: ChatViewModel,
    modifier: Modifier = Modifier
) {
    val workerStatus by viewModel.workerStatus.collectAsState()

    Scaffold(
        topBar = {
            TopAppBar(
                title = {
                    Text(
                        "Worker Node Telemetry",
                        fontWeight = FontWeight.Bold,
                        fontSize = 18.sp,
                        color = Color.White
                    )
                },
                actions = {
                    IconButton(onClick = { viewModel.checkWorkerNodeHealth() }) {
                        Icon(
                            imageVector = Icons.Default.Refresh,
                            contentDescription = "Refresh",
                            tint = Color.White
                        )
                    }
                },
                colors = TopAppBarDefaults.topAppBarColors(
                    containerColor = Color(0xFF0A0D14)
                )
            )
        },
        containerColor = Color(0xFF0A0D14),
        modifier = modifier
    ) { innerPadding ->
        Column(
            modifier = Modifier
                .fillMaxSize()
                .padding(innerPadding)
                .padding(16.dp),
            verticalArrangement = Arrangement.spacedBy(16.dp)
        ) {
            // Main Status Banner
            Card(
                shape = RoundedCornerShape(16.dp),
                colors = CardDefaults.cardColors(containerColor = Color(0xFF111625)),
                modifier = Modifier
                    .fillMaxWidth()
                    .border(1.dp, Color(0xFF1E2638), RoundedCornerShape(16.dp))
            ) {
                Column(modifier = Modifier.padding(16.dp)) {
                    Row(
                        verticalAlignment = Alignment.CenterVertically,
                        horizontalArrangement = Arrangement.SpaceBetween,
                        modifier = Modifier.fillMaxWidth()
                    ) {
                        Row(verticalAlignment = Alignment.CenterVertically) {
                            Box(
                                modifier = Modifier
                                    .size(12.dp)
                                    .clip(CircleShape)
                                    .background(if (workerStatus.isOnline) Color(0xFF10B981) else Color(0xFFEF4444))
                            )
                            Spacer(modifier = Modifier.width(8.dp))
                            Text(
                                if (workerStatus.isOnline) "NODE ONLINE" else "NODE OFFLINE",
                                fontWeight = FontWeight.Bold,
                                color = if (workerStatus.isOnline) Color(0xFF10B981) else Color(0xFFEF4444),
                                fontSize = 14.sp
                            )
                        }

                        if (workerStatus.isOnline) {
                            Surface(
                                shape = RoundedCornerShape(12.dp),
                                color = Color(0xFF064E3B)
                            ) {
                                Text(
                                    "${workerStatus.latencyMs} ms",
                                    modifier = Modifier.padding(horizontal = 8.dp, vertical = 4.dp),
                                    color = Color(0xFF34D399),
                                    fontSize = 11.sp,
                                    fontWeight = FontWeight.SemiBold
                                )
                            }
                        }
                    }

                    Spacer(modifier = Modifier.height(12.dp))

                    Text(
                        "Target: ${workerStatus.gatewayUrl}",
                        color = Color(0xFF94A3B8),
                        fontSize = 13.sp,
                        fontFamily = FontFamily.Monospace
                    )

                    Spacer(modifier = Modifier.height(4.dp))

                    Text(
                        "Status: ${workerStatus.statusMessage}",
                        color = Color.White,
                        fontSize = 14.sp,
                        fontWeight = FontWeight.Medium
                    )

                    if (workerStatus.lastChecked > 0) {
                        Spacer(modifier = Modifier.height(8.dp))
                        val formattedTime = SimpleDateFormat("HH:mm:ss", Locale.getDefault())
                            .format(Date(workerStatus.lastChecked))
                        Text(
                            "Last probed at $formattedTime",
                            color = Color(0xFF64748B),
                            fontSize = 11.sp
                        )
                    }
                }
            }

            // Services Grid
            Text(
                "Active Subsystems",
                fontWeight = FontWeight.Bold,
                color = Color.White,
                fontSize = 15.sp
            )

            ServiceRowItem(
                name = "Nginx Reverse Proxy Gateway",
                endpoint = ":8081",
                isActive = workerStatus.isOnline,
                details = "Gzip, SSE chunked streaming, static React SPA"
            )

            ServiceRowItem(
                name = "FastAPI / Uvicorn Core",
                endpoint = ":8001 (Internal)",
                isActive = workerStatus.isOnline,
                details = "Dual-Key failover, Google GenAI SDK, SQLite"
            )

            ServiceRowItem(
                name = "Android Embedded Server",
                endpoint = ":8080 (Local)",
                isActive = true,
                details = "Embedded HTTP daemon on device"
            )

            Spacer(modifier = Modifier.weight(1f))

            Button(
                onClick = { viewModel.checkWorkerNodeHealth() },
                modifier = Modifier
                    .fillMaxWidth()
                    .height(48.dp),
                shape = RoundedCornerShape(12.dp),
                colors = ButtonDefaults.buttonColors(containerColor = Color(0xFF0284C7))
            ) {
                Icon(Icons.Default.Router, contentDescription = null, modifier = Modifier.size(18.dp))
                Spacer(modifier = Modifier.width(8.dp))
                Text("Ping & Probe Worker Health", fontWeight = FontWeight.Bold)
            }
        }
    }
}

@Composable
fun ServiceRowItem(
    name: String,
    endpoint: String,
    isActive: Boolean,
    details: String
) {
    Surface(
        shape = RoundedCornerShape(12.dp),
        color = Color(0xFF111625),
        border = androidx.compose.foundation.BorderStroke(1.dp, Color(0xFF1E2638)),
        modifier = Modifier.fillMaxWidth()
    ) {
        Row(
            modifier = Modifier.padding(14.dp),
            verticalAlignment = Alignment.CenterVertically
        ) {
            Icon(
                imageVector = if (isActive) Icons.Default.CheckCircle else Icons.Default.Error,
                contentDescription = null,
                tint = if (isActive) Color(0xFF10B981) else Color(0xFFEF4444),
                modifier = Modifier.size(24.dp)
            )

            Spacer(modifier = Modifier.width(12.dp))

            Column(modifier = Modifier.weight(1f)) {
                Row(
                    verticalAlignment = Alignment.CenterVertically,
                    horizontalArrangement = Arrangement.SpaceBetween,
                    modifier = Modifier.fillMaxWidth()
                ) {
                    Text(name, fontWeight = FontWeight.SemiBold, color = Color.White, fontSize = 13.sp)
                    Text(endpoint, color = Color(0xFF00D2FF), fontSize = 11.sp, fontFamily = FontFamily.Monospace)
                }
                Spacer(modifier = Modifier.height(2.dp))
                Text(details, color = Color(0xFF64748B), fontSize = 11.sp)
            }
        }
    }
}
