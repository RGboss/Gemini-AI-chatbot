package com.orbit.chatbot.network

import android.content.Context
import android.util.Log
import com.orbit.chatbot.data.SettingsRepository
import kotlinx.coroutines.CoroutineScope
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.flow.first
import kotlinx.coroutines.launch
import org.json.JSONArray
import org.json.JSONObject
import java.io.*
import java.net.ServerSocket
import java.net.Socket
import java.util.concurrent.Executors

class EmbeddedHttpServer(
    private val context: Context,
    private val port: Int = 8080
) {
    private val TAG = "EmbeddedHttpServer"
    private var serverSocket: ServerSocket? = null
    private var isRunning = false
    private val threadPool = Executors.newFixedThreadPool(8)
    private val settingsRepo = SettingsRepository(context)
    private val chatService = GeminiChatService()

    fun start() {
        if (isRunning) return
        isRunning = true
        Thread {
            try {
                serverSocket = ServerSocket(port)
                Log.i(TAG, "Orbit Chatbot embedded server started on port $port")
                while (isRunning) {
                    val client = serverSocket?.accept() ?: break
                    threadPool.execute { handleClient(client) }
                }
            } catch (e: Exception) {
                if (isRunning) {
                    Log.e(TAG, "Server error: ${e.message}", e)
                }
            }
        }.start()
    }

    fun stop() {
        isRunning = false
        try {
            serverSocket?.close()
        } catch (e: Exception) {
            Log.e(TAG, "Error closing server socket", e)
        }
    }

    private fun handleClient(client: Socket) {
        try {
            val reader = BufferedReader(InputStreamReader(client.getInputStream()))
            val output = client.getOutputStream()

            val requestLine = reader.readLine() ?: return
            val parts = requestLine.split(" ")
            if (parts.size < 2) return

            val method = parts[0]
            val path = parts[1].split("?")[0]

            // Read headers
            val headers = mutableMapOf<String, String>()
            var contentLength = 0
            var line: String?
            while (reader.readLine().also { line = it } != null) {
                if (line.isNullOrEmpty()) break
                val headerParts = line!!.split(": ", limit = 2)
                if (headerParts.size == 2) {
                    headers[headerParts[0].lowercase()] = headerParts[1]
                    if (headerParts[0].equals("content-length", ignoreCase = true)) {
                        contentLength = headerParts[1].trim().toIntOrNull() ?: 0
                    }
                }
            }

            // Handle OPTIONS for CORS
            if (method.equals("OPTIONS", ignoreCase = true)) {
                sendResponse(output, 204, "No Content", "text/plain", ByteArray(0))
                return
            }

            // REST API Routes
            when {
                path == "/health" -> {
                    val body = """{"status":"healthy","app":"orbit-chatbot-android","mode":"android-embedded"}"""
                    sendResponse(output, 200, "OK", "application/json", body.toByteArray())
                    return
                }
                path == "/api/health" -> {
                    val body = """{"status":"ok","app":"orbit-chatbot","version":"2.5.0-android","embedded":true}"""
                    sendResponse(output, 200, "OK", "application/json", body.toByteArray())
                    return
                }
                path == "/api/models" -> {
                    val json = JSONObject().apply {
                        put("models", JSONArray().apply {
                            put("gemini-2.5-flash")
                            put("gemini-2.5-pro")
                            put("gemini-1.5-flash")
                            put("gemini-3.5-flash")
                        })
                    }
                    sendResponse(output, 200, "OK", "application/json", json.toString().toByteArray())
                    return
                }
                path == "/api/chat" && method.equals("POST", ignoreCase = true) -> {
                    // Read request body
                    val charArray = CharArray(contentLength)
                    reader.read(charArray, 0, contentLength)
                    val requestBody = String(charArray)
                    handleChatApi(output, requestBody)
                    return
                }
                else -> {
                    // Static Frontend File Serving
                    serveStaticAsset(output, path)
                }
            }
        } catch (e: Exception) {
            Log.e(TAG, "Client handle error", e)
        } finally {
            try { client.close() } catch (ignored: Exception) {}
        }
    }

    private fun handleChatApi(output: OutputStream, requestBody: String) {
        try {
            val json = JSONObject(requestBody)
            val prompt = json.optString("message", "")

            CoroutineScope(Dispatchers.IO).launch {
                val orchestratorKey = settingsRepo.orchestratorKeyFlow.first()
                val workerKey = settingsRepo.workerKeyFlow.first()
                val selectedModel = settingsRepo.selectedModelFlow.first()

                var fullReply = ""
                chatService.sendMessageStream(prompt, listOf(workerKey, orchestratorKey), selectedModel)
                    .collect { chunk -> fullReply += chunk }

                val responseJson = JSONObject().apply {
                    put("reply", fullReply)
                    put("sources", JSONArray())
                    put("confidence", JSONObject().apply {
                        put("score", 1.0)
                        put("level", "HIGH")
                        put("percentage", 100)
                    })
                }
                sendResponse(output, 200, "OK", "application/json", responseJson.toString().toByteArray())
            }
        } catch (e: Exception) {
            val errJson = JSONObject().apply { put("error", e.localizedMessage ?: "Chat processing error") }
            sendResponse(output, 500, "Internal Server Error", "application/json", errJson.toString().toByteArray())
        }
    }

    private fun serveStaticAsset(output: OutputStream, rawPath: String) {
        var filePath = rawPath.removePrefix("/")
        if (filePath.isEmpty()) filePath = "index.html"

        val assetPath = "web/$filePath"
        try {
            val inputStream = context.assets.open(assetPath)
            val bytes = inputStream.readBytes()
            val mime = getMimeType(filePath)
            sendResponse(output, 200, "OK", mime, bytes)
        } catch (e: FileNotFoundException) {
            // SPA routing fallback: return index.html for frontend client routes
            try {
                val indexStream = context.assets.open("web/index.html")
                val bytes = indexStream.readBytes()
                sendResponse(output, 200, "OK", "text/html", bytes)
            } catch (fallbackError: Exception) {
                sendResponse(output, 404, "Not Found", "text/plain", "Asset not found".toByteArray())
            }
        }
    }

    private fun getMimeType(path: String): String {
        return when {
            path.endsWith(".html") -> "text/html; charset=UTF-8"
            path.endsWith(".js") -> "application/javascript; charset=UTF-8"
            path.endsWith(".css") -> "text/css; charset=UTF-8"
            path.endsWith(".json") -> "application/json; charset=UTF-8"
            path.endsWith(".png") -> "image/png"
            path.endsWith(".jpg") || path.endsWith(".jpeg") -> "image/jpeg"
            path.endsWith(".svg") -> "image/svg+xml"
            path.endsWith(".ico") -> "image/x-icon"
            path.endsWith(".woff2") -> "font/woff2"
            path.endsWith(".woff") -> "font/woff"
            path.endsWith(".ttf") -> "font/ttf"
            else -> "application/octet-stream"
        }
    }

    private fun sendResponse(
        output: OutputStream,
        statusCode: Int,
        statusText: String,
        contentType: String,
        body: ByteArray
    ) {
        val writer = PrintWriter(output)
        writer.print("HTTP/1.1 $statusCode $statusText\r\n")
        writer.print("Content-Type: $contentType\r\n")
        writer.print("Content-Length: ${body.size}\r\n")
        writer.print("Connection: close\r\n")
        writer.print("Access-Control-Allow-Origin: *\r\n")
        writer.print("Access-Control-Allow-Methods: GET, POST, OPTIONS\r\n")
        writer.print("Access-Control-Allow-Headers: *\r\n")
        writer.print("\r\n")
        writer.flush()

        output.write(body)
        output.flush()
    }
}
