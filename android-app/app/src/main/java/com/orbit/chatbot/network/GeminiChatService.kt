package com.orbit.chatbot.network

import com.google.ai.client.generativeai.GenerativeModel
import com.google.ai.client.generativeai.type.content
import kotlinx.coroutines.flow.Flow
import kotlinx.coroutines.flow.flow
import okhttp3.MediaType.Companion.toMediaType
import okhttp3.OkHttpClient
import okhttp3.Request
import okhttp3.RequestBody.Companion.toRequestBody
import org.json.JSONArray
import org.json.JSONObject
import java.io.IOException
import java.util.concurrent.TimeUnit

class GeminiChatService {

    private val httpClient = OkHttpClient.Builder()
        .connectTimeout(30, TimeUnit.SECONDS)
        .readTimeout(60, TimeUnit.SECONDS)
        .writeTimeout(30, TimeUnit.SECONDS)
        .build()

    private val systemInstruction = """
        You are Orbit, an elite enterprise AI workspace copilot and engineering assistant.
        You provide fast, highly accurate, structured technical and business insights.
        Use clean Markdown with bold headings, bullet points, and syntax-highlighted code blocks.
    """.trimIndent()

    /**
     * Generates a streaming response with automatic dual-key failover and model fallback.
     */
    fun sendMessageStream(
        prompt: String,
        candidateKeys: List<String>,
        primaryModel: String = "gemini-3.5-flash"
    ): Flow<String> = flow {
        val keys = candidateKeys.filter { it.isNotBlank() }
        if (keys.isEmpty()) {
            emit("Error: No Gemini API keys configured. Please configure your key in Settings.")
            return@flow
        }

        val modelsToTry = listOf(primaryModel, "gemini-3.5-flash", "gemini-3.8-flash", "gemini-2.5-pro", "gemini-2.5-flash")
            .distinct()

        var lastError: Exception? = null
        var streamedAny = false

        for (modelName in modelsToTry) {
            for (key in keys) {
                try {
                    // Try official Google Generative AI SDK
                    val model = GenerativeModel(
                        modelName = modelName,
                        apiKey = key,
                        systemInstruction = content { text(systemInstruction) }
                    )

                    model.generateContentStream(prompt).collect { chunk ->
                        chunk.text?.let { text ->
                            if (text.isNotEmpty()) {
                                streamedAny = true
                                emit(text)
                            }
                        }
                    }

                    if (streamedAny) return@flow
                } catch (e: Exception) {
                    lastError = e
                    // If we haven't emitted anything yet, try the next key or model
                    if (!streamedAny) {
                        continue
                    } else {
                        emit("\n\n*[Connection interrupted: ${e.localizedMessage ?: "Network error"}]*")
                        return@flow
                    }
                }
            }
        }

        // If SDK failed before streaming, try direct REST endpoint as robust failover
        if (!streamedAny) {
            for (key in keys) {
                try {
                    val restResponse = callRestApi(prompt, key, primaryModel)
                    emit(restResponse)
                    return@flow
                } catch (e: Exception) {
                    lastError = e
                }
            }
            emit("Unable to reach Gemini API after trying ${keys.size} keys: ${lastError?.message ?: "Unknown error"}")
        }
    }

    private fun callRestApi(prompt: String, apiKey: String, model: String): String {
        val url = "https://generativelanguage.googleapis.com/v1beta/models/$model:generateContent?key=$apiKey"
        val payload = JSONObject().apply {
            put("contents", JSONArray().apply {
                put(JSONObject().apply {
                    put("parts", JSONArray().apply {
                        put(JSONObject().put("text", prompt))
                    })
                })
            })
            put("systemInstruction", JSONObject().apply {
                put("parts", JSONArray().apply {
                    put(JSONObject().put("text", systemInstruction))
                })
            })
        }

        val request = Request.Builder()
            .url(url)
            .post(payload.toString().toRequestBody("application/json".toMediaType()))
            .build()

        httpClient.newCall(request).execute().use { response ->
            if (!response.isSuccessful) {
                throw IOException("REST API Error HTTP ${response.code}: ${response.body?.string()}")
            }
            val body = response.body?.string() ?: throw IOException("Empty response")
            val json = JSONObject(body)
            val candidates = json.optJSONArray("candidates")
            if (candidates != null && candidates.length() > 0) {
                val content = candidates.getJSONObject(0).optJSONObject("content")
                val parts = content?.optJSONArray("parts")
                if (parts != null && parts.length() > 0) {
                    return parts.getJSONObject(0).optString("text", "")
                }
            }
            return "No response content received."
        }
    }
}
