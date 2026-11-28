package com.orbit.chatbot.data

import android.content.Context
import androidx.datastore.core.DataStore
import androidx.datastore.preferences.core.Preferences
import androidx.datastore.preferences.core.edit
import androidx.datastore.preferences.core.stringPreferencesKey
import androidx.datastore.preferences.preferencesDataStore
import kotlinx.coroutines.flow.Flow
import kotlinx.coroutines.flow.map

val Context.dataStore: DataStore<Preferences> by preferencesDataStore(name = "orbit_settings")

class SettingsRepository(private val context: Context) {

    companion object {
        val KEY_ORCHESTRATOR = stringPreferencesKey("gemini_orchestrator_key")
        val KEY_WORKER = stringPreferencesKey("gemini_worker_key")
        val KEY_GOOGLE = stringPreferencesKey("google_api_key")
        val KEY_SELECTED_MODEL = stringPreferencesKey("selected_model")
        val KEY_GATEWAY_URL = stringPreferencesKey("gateway_url")
        val KEY_EMBEDDED_URL = stringPreferencesKey("embedded_url")

        // Default credentials (configured via Settings or DataStore seeding)
        const val DEFAULT_ORCHESTRATOR_KEY = ""
        const val DEFAULT_WORKER_KEY = ""
        const val DEFAULT_MODEL = "gemini-3.5-flash"
        const val DEFAULT_GATEWAY_URL = "http://192.168.29.94:8081"
        const val DEFAULT_EMBEDDED_URL = "http://127.0.0.1:8080"
    }

    val orchestratorKeyFlow: Flow<String> = context.dataStore.data.map { prefs ->
        prefs[KEY_ORCHESTRATOR] ?: DEFAULT_ORCHESTRATOR_KEY
    }

    val workerKeyFlow: Flow<String> = context.dataStore.data.map { prefs ->
        prefs[KEY_WORKER] ?: DEFAULT_WORKER_KEY
    }

    val googleKeyFlow: Flow<String> = context.dataStore.data.map { prefs ->
        prefs[KEY_GOOGLE] ?: DEFAULT_WORKER_KEY
    }

    val selectedModelFlow: Flow<String> = context.dataStore.data.map { prefs ->
        prefs[KEY_SELECTED_MODEL] ?: DEFAULT_MODEL
    }

    val gatewayUrlFlow: Flow<String> = context.dataStore.data.map { prefs ->
        prefs[KEY_GATEWAY_URL] ?: DEFAULT_GATEWAY_URL
    }

    val embeddedUrlFlow: Flow<String> = context.dataStore.data.map { prefs ->
        prefs[KEY_EMBEDDED_URL] ?: DEFAULT_EMBEDDED_URL
    }

    suspend fun saveOrchestratorKey(key: String) {
        context.dataStore.edit { it[KEY_ORCHESTRATOR] = key }
    }

    suspend fun saveWorkerKey(key: String) {
        context.dataStore.edit { it[KEY_WORKER] = key }
    }

    suspend fun saveGoogleKey(key: String) {
        context.dataStore.edit { it[KEY_GOOGLE] = key }
    }

    suspend fun saveSelectedModel(model: String) {
        context.dataStore.edit { it[KEY_SELECTED_MODEL] = model }
    }

    suspend fun saveGatewayUrl(url: String) {
        context.dataStore.edit { it[KEY_GATEWAY_URL] = url }
    }

    suspend fun clearKeys() {
        context.dataStore.edit {
            it.remove(KEY_ORCHESTRATOR)
            it.remove(KEY_WORKER)
            it.remove(KEY_GOOGLE)
        }
    }
}
