package com.orbit.chatbot.data

import kotlinx.serialization.Serializable
import java.util.UUID

@Serializable
data class ChatMessage(
    val id: String = UUID.randomUUID().toString(),
    val role: String, // "user" or "model"
    val text: String,
    val timestamp: Long = System.currentTimeMillis(),
    val model: String? = null,
    val latencyMs: Long? = null,
    val isStreaming: Boolean = false
)

data class ModelInfo(
    val id: String,
    val name: String,
    val badge: String,
    val description: String
)

val AVAILABLE_MODELS = listOf(
    ModelInfo("gemini-3.5-flash", "Gemini 3.5 Flash", "Default", "High volume, low cost, specialized enterprise tier"),
    ModelInfo("gemini-3.8-flash", "Gemini 3.8 Flash", "Fast", "Latest generation low-latency enterprise model"),
    ModelInfo("gemini-2.5-pro", "Gemini 2.5 Pro", "Pro Reasoning", "Deep reasoning for complex multi-step workflows"),
    ModelInfo("gemini-2.5-flash", "Gemini 2.5 Flash", "Multimodal", "Ultra-fast response, cutting-edge multimodal reasoning")
)

data class WorkerNodeStatus(
    val isOnline: Boolean = false,
    val latencyMs: Long = -1,
    val statusMessage: String = "Connecting…",
    val gatewayUrl: String = "http://192.168.29.94:8081",
    val backendStatus: String = "unknown",
    val lastChecked: Long = 0
)

val QUICK_PROMPTS = listOf(
    "Analyze project architecture & deployment topology",
    "Verify dual-key API resilience & failover",
    "Ping worker gateway at 192.168.29.94:8081",
    "Explain RAG vector search & document ingestion",
    "Draft executive summary for Orbit AI workspace",
    "Benchmark Gemini response speed & token throughput"
)
