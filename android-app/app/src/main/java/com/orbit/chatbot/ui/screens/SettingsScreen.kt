package com.orbit.chatbot.ui.screens

import android.widget.Toast
import androidx.compose.foundation.background
import androidx.compose.foundation.border
import androidx.compose.foundation.layout.*
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.foundation.verticalScroll
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.filled.Check
import androidx.compose.material.icons.filled.Delete
import androidx.compose.material.icons.filled.Key
import androidx.compose.material.icons.filled.Security
import androidx.compose.material3.*
import androidx.compose.runtime.*
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.text.font.FontFamily
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import com.orbit.chatbot.data.AVAILABLE_MODELS
import com.orbit.chatbot.data.SettingsRepository
import kotlinx.coroutines.flow.first
import kotlinx.coroutines.launch

@OptIn(ExperimentalMaterial3Api::class)
@Composable
fun SettingsScreen(
    modifier: Modifier = Modifier
) {
    val context = LocalContext.current
    val settingsRepo = remember { SettingsRepository(context) }
    val coroutineScope = rememberCoroutineScope()
    val scrollState = rememberScrollState()

    var orchestratorKey by remember { mutableStateOf("") }
    var workerKey by remember { mutableStateOf("") }
    var selectedModel by remember { mutableStateOf("gemini-2.5-flash") }
    var gatewayUrl by remember { mutableStateOf("http://192.168.29.94:8081") }
    var modelDropdownExpanded by remember { mutableStateOf(false) }

    LaunchedEffect(Unit) {
        orchestratorKey = settingsRepo.orchestratorKeyFlow.first()
        workerKey = settingsRepo.workerKeyFlow.first()
        selectedModel = settingsRepo.selectedModelFlow.first()
        gatewayUrl = settingsRepo.gatewayUrlFlow.first()
    }

    Scaffold(
        topBar = {
            TopAppBar(
                title = {
                    Text(
                        "Settings & Credentials",
                        fontWeight = FontWeight.Bold,
                        fontSize = 18.sp,
                        color = Color.White
                    )
                },
                colors = TopAppBarDefaults.topAppBarColors(containerColor = Color(0xFF0A0D14))
            )
        },
        containerColor = Color(0xFF0A0D14),
        modifier = modifier
    ) { innerPadding ->
        Column(
            modifier = Modifier
                .fillMaxSize()
                .padding(innerPadding)
                .verticalScroll(scrollState)
                .padding(16.dp),
            verticalArrangement = Arrangement.spacedBy(16.dp)
        ) {
            // Security Card
            Card(
                shape = RoundedCornerShape(12.dp),
                colors = CardDefaults.cardColors(containerColor = Color(0xFF111625)),
                modifier = Modifier
                    .fillMaxWidth()
                    .border(1.dp, Color(0xFF1E2638), RoundedCornerShape(12.dp))
            ) {
                Row(modifier = Modifier.padding(14.dp), verticalAlignment = Alignment.CenterVertically) {
                    Icon(
                        imageVector = Icons.Default.Security,
                        contentDescription = null,
                        tint = Color(0xFF00D2FF),
                        modifier = Modifier.size(24.dp)
                    )
                    Spacer(modifier = Modifier.width(12.dp))
                    Text(
                        "Credentials stored securely on-device using Jetpack DataStore Preferences. Keys are never transmitted to third parties.",
                        fontSize = 12.sp,
                        color = Color(0xFFCBD5E1),
                        lineHeight = 16.sp
                    )
                }
            }

            // Orchestrator Key
            Text("Gemini Orchestrator Key", color = Color.White, fontWeight = FontWeight.SemiBold, fontSize = 13.sp)
            OutlinedTextField(
                value = orchestratorKey,
                onValueChange = { orchestratorKey = it },
                placeholder = { Text("AIzaSy…", color = Color(0xFF64748B)) },
                leadingIcon = { Icon(Icons.Default.Key, contentDescription = null, tint = Color(0xFF00D2FF)) },
                modifier = Modifier.fillMaxWidth(),
                colors = OutlinedTextFieldDefaults.colors(
                    focusedBorderColor = Color(0xFF00D2FF),
                    unfocusedBorderColor = Color(0xFF334155),
                    focusedContainerColor = Color(0xFF111625),
                    unfocusedContainerColor = Color(0xFF111625),
                    focusedTextColor = Color.White,
                    unfocusedTextColor = Color.White
                ),
                shape = RoundedCornerShape(12.dp),
                singleLine = true
            )

            // Worker Key
            Text("Gemini Worker Key (Failover)", color = Color.White, fontWeight = FontWeight.SemiBold, fontSize = 13.sp)
            OutlinedTextField(
                value = workerKey,
                onValueChange = { workerKey = it },
                placeholder = { Text("AQ.Ab8…", color = Color(0xFF64748B)) },
                leadingIcon = { Icon(Icons.Default.Key, contentDescription = null, tint = Color(0xFF818CF8)) },
                modifier = Modifier.fillMaxWidth(),
                colors = OutlinedTextFieldDefaults.colors(
                    focusedBorderColor = Color(0xFF818CF8),
                    unfocusedBorderColor = Color(0xFF334155),
                    focusedContainerColor = Color(0xFF111625),
                    unfocusedContainerColor = Color(0xFF111625),
                    focusedTextColor = Color.White,
                    unfocusedTextColor = Color.White
                ),
                shape = RoundedCornerShape(12.dp),
                singleLine = true
            )

            // Model Selection
            Text("Primary AI Model", color = Color.White, fontWeight = FontWeight.SemiBold, fontSize = 13.sp)
            ExposedDropdownMenuBox(
                expanded = modelDropdownExpanded,
                onExpandedChange = { modelDropdownExpanded = !modelDropdownExpanded }
            ) {
                OutlinedTextField(
                    value = selectedModel,
                    onValueChange = {},
                    readOnly = true,
                    modifier = Modifier
                        .fillMaxWidth()
                        .menuAnchor(),
                    trailingIcon = { ExposedDropdownMenuDefaults.TrailingIcon(expanded = modelDropdownExpanded) },
                    colors = OutlinedTextFieldDefaults.colors(
                        focusedBorderColor = Color(0xFF00D2FF),
                        unfocusedBorderColor = Color(0xFF334155),
                        focusedContainerColor = Color(0xFF111625),
                        unfocusedContainerColor = Color(0xFF111625),
                        focusedTextColor = Color.White,
                        unfocusedTextColor = Color.White
                    ),
                    shape = RoundedCornerShape(12.dp)
                )

                ExposedDropdownMenu(
                    expanded = modelDropdownExpanded,
                    onDismissRequest = { modelDropdownExpanded = false }
                ) {
                    AVAILABLE_MODELS.forEach { model ->
                        DropdownMenuItem(
                            text = {
                                Column {
                                    Text(model.name, fontWeight = FontWeight.Bold, color = Color.White)
                                    Text(model.description, fontSize = 11.sp, color = Color(0xFF94A3B8))
                                }
                            },
                            onClick = {
                                selectedModel = model.id
                                modelDropdownExpanded = false
                            }
                        )
                    }
                }
            }

            // Gateway URL
            Text("Worker Gateway URL", color = Color.White, fontWeight = FontWeight.SemiBold, fontSize = 13.sp)
            OutlinedTextField(
                value = gatewayUrl,
                onValueChange = { gatewayUrl = it },
                placeholder = { Text("http://192.168.29.94:8081", color = Color(0xFF64748B)) },
                modifier = Modifier.fillMaxWidth(),
                colors = OutlinedTextFieldDefaults.colors(
                    focusedBorderColor = Color(0xFF00D2FF),
                    unfocusedBorderColor = Color(0xFF334155),
                    focusedContainerColor = Color(0xFF111625),
                    unfocusedContainerColor = Color(0xFF111625),
                    focusedTextColor = Color.White,
                    unfocusedTextColor = Color.White
                ),
                shape = RoundedCornerShape(12.dp),
                singleLine = true
            )

            Spacer(modifier = Modifier.height(8.dp))

            // Action Buttons
            Button(
                onClick = {
                    coroutineScope.launch {
                        settingsRepo.saveOrchestratorKey(orchestratorKey.trim())
                        settingsRepo.saveWorkerKey(workerKey.trim())
                        settingsRepo.saveSelectedModel(selectedModel)
                        settingsRepo.saveGatewayUrl(gatewayUrl.trim())
                        Toast.makeText(context, "Settings saved successfully", Toast.LENGTH_SHORT).show()
                    }
                },
                modifier = Modifier
                    .fillMaxWidth()
                    .height(48.dp),
                shape = RoundedCornerShape(12.dp),
                colors = ButtonDefaults.buttonColors(containerColor = Color(0xFF0284C7))
            ) {
                Icon(Icons.Default.Check, contentDescription = null, modifier = Modifier.size(18.dp))
                Spacer(modifier = Modifier.width(8.dp))
                Text("Save Credentials & Preferences", fontWeight = FontWeight.Bold)
            }

            OutlinedButton(
                onClick = {
                    coroutineScope.launch {
                        settingsRepo.clearKeys()
                        orchestratorKey = SettingsRepository.DEFAULT_ORCHESTRATOR_KEY
                        workerKey = SettingsRepository.DEFAULT_WORKER_KEY
                        selectedModel = SettingsRepository.DEFAULT_MODEL
                        gatewayUrl = SettingsRepository.DEFAULT_GATEWAY_URL
                        settingsRepo.saveOrchestratorKey(orchestratorKey)
                        settingsRepo.saveWorkerKey(workerKey)
                        settingsRepo.saveSelectedModel(selectedModel)
                        settingsRepo.saveGatewayUrl(gatewayUrl)
                        Toast.makeText(context, "Reset to default credentials", Toast.LENGTH_SHORT).show()
                    }
                },
                modifier = Modifier
                    .fillMaxWidth()
                    .height(48.dp),
                shape = RoundedCornerShape(12.dp),
                colors = ButtonDefaults.outlinedButtonColors(contentColor = Color(0xFFEF4444)),
                border = androidx.compose.foundation.BorderStroke(1.dp, Color(0xFFEF4444))
            ) {
                Icon(Icons.Default.Delete, contentDescription = null, modifier = Modifier.size(18.dp))
                Spacer(modifier = Modifier.width(8.dp))
                Text("Reset to Default Working Keys", fontWeight = FontWeight.Medium)
            }
        }
    }
}
