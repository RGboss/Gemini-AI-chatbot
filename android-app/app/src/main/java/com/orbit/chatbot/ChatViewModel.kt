package com.orbit.chatbot

import android.app.Application
import androidx.lifecycle.AndroidViewModel
import androidx.lifecycle.viewModelScope
import com.orbit.chatbot.data.ChatMessage
import com.orbit.chatbot.data.SettingsRepository
import com.orbit.chatbot.data.WorkerNodeStatus
import com.orbit.chatbot.network.GeminiChatService
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.asStateFlow
import kotlinx.coroutines.flow.first
import kotlinx.coroutines.launch
import okhttp3.OkHttpClient
import okhttp3.Request
import java.util.concurrent.TimeUnit

class ChatViewModel(application: Application) : AndroidViewModel(application) {

    private val settingsRepo = SettingsRepository(application)
    private val chatService = GeminiChatService()
    private val httpClient = OkHttpClient.Builder()
        .connectTimeout(5, TimeUnit.SECONDS)
        .readTimeout(10, TimeUnit.SECONDS)
        .build()

    private val _messages = MutableStateFlow<List<ChatMessage>>(
        listOf(
            ChatMessage(
                role = "model",
                text = "### Welcome to Orbit AI Copilot\n\nI am your autonomous enterprise workspace assistant. I can help analyze system architecture, draft code, inspect deployment logs, and run high-volume queries with automated fallback resilience.\n\n*Choose a quick prompt below or type your instruction to begin.*",
                model = "gemini-2.5-flash"
            )
        )
    )
    val messages: StateFlow<List<ChatMessage>> = _messages.asStateFlow()

    private val _isGenerating = MutableStateFlow(false)
    val isGenerating: StateFlow<Boolean> = _isGenerating.asStateFlow()

    private val _workerStatus = MutableStateFlow(WorkerNodeStatus())
    val workerStatus: StateFlow<WorkerNodeStatus> = _workerStatus.asStateFlow()

    init {
        checkWorkerNodeHealth()
    }

    fun sendMessage(text: String) {
        val trimmed = text.trim()
        if (trimmed.isEmpty() || _isGenerating.value) return

        val userMsg = ChatMessage(role = "user", text = trimmed)
        val assistantMsgId = java.util.UUID.randomUUID().toString()

        _messages.value = _messages.value + userMsg
        _isGenerating.value = true

        viewModelScope.launch(Dispatchers.IO) {
            val startTime = System.currentTimeMillis()
            val orchestratorKey = settingsRepo.orchestratorKeyFlow.first()
            val workerKey = settingsRepo.workerKeyFlow.first()
            val googleKey = settingsRepo.googleKeyFlow.first()
            val selectedModel = settingsRepo.selectedModelFlow.first()

            val candidateKeys = listOf(workerKey, googleKey, orchestratorKey)
                .filter { it.isNotBlank() }
                .distinct()

            // Temporary placeholder message while streaming
            var accumulatedText = ""
            val placeholder = ChatMessage(
                id = assistantMsgId,
                role = "model",
                text = "...",
                model = selectedModel,
                isStreaming = true
            )
            _messages.value = _messages.value + placeholder

            try {
                chatService.sendMessageStream(trimmed, candidateKeys, selectedModel)
                    .collect { chunk ->
                        accumulatedText += chunk
                        _messages.value = _messages.value.map { msg ->
                            if (msg.id == assistantMsgId) {
                                msg.copy(
                                    text = accumulatedText,
                                    latencyMs = System.currentTimeMillis() - startTime
                                )
                            } else msg
                        }
                    }
            } catch (e: Exception) {
                accumulatedText = "Error during generation: ${e.localizedMessage ?: "Unknown network failure"}"
            } finally {
                val totalLatency = System.currentTimeMillis() - startTime
                _messages.value = _messages.value.map { msg ->
                    if (msg.id == assistantMsgId) {
                        msg.copy(
                            text = if (accumulatedText.isEmpty()) "No response generated." else accumulatedText,
                            latencyMs = totalLatency,
                            isStreaming = false
                        )
                    } else msg
                }
                _isGenerating.value = false
            }
        }
    }

    fun clearChat() {
        _messages.value = listOf(
            ChatMessage(
                role = "model",
                text = "Chat cleared. Ready for your next instruction.",
                model = "Orbit AI"
            )
        )
    }

    fun checkWorkerNodeHealth() {
        viewModelScope.launch(Dispatchers.IO) {
            val gatewayUrl = settingsRepo.gatewayUrlFlow.first()
            val startTime = System.currentTimeMillis()

            try {
                val request = Request.Builder()
                    .url("$gatewayUrl/health")
                    .get()
                    .build()

                httpClient.newCall(request).execute().use { response ->
                    val elapsed = System.currentTimeMillis() - startTime
                    if (response.isSuccessful) {
                        val body = response.body?.string() ?: ""
                        _workerStatus.value = WorkerNodeStatus(
                            isOnline = true,
                            latencyMs = elapsed,
                            statusMessage = "Online (HTTP ${response.code})",
                            gatewayUrl = gatewayUrl,
                            backendStatus = if (body.contains("healthy")) "Healthy" else "Active",
                            lastChecked = System.currentTimeMillis()
                        )
                    } else {
                        _workerStatus.value = WorkerNodeStatus(
                            isOnline = false,
                            latencyMs = elapsed,
                            statusMessage = "HTTP Error ${response.code}",
                            gatewayUrl = gatewayUrl,
                            lastChecked = System.currentTimeMillis()
                        )
                    }
                }
            } catch (e: Exception) {
                _workerStatus.value = WorkerNodeStatus(
                    isOnline = false,
                    latencyMs = -1,
                    statusMessage = e.localizedMessage ?: "Connection Refused",
                    gatewayUrl = gatewayUrl,
                    lastChecked = System.currentTimeMillis()
                )
            }
        }
    }
}
