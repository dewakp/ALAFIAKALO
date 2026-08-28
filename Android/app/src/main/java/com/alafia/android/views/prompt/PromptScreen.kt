package com.alafia.android.views.prompt

import android.content.ContentResolver
import android.content.Intent
import android.net.Uri
import android.speech.RecognizerIntent
import androidx.activity.compose.rememberLauncherForActivityResult
import androidx.activity.result.contract.ActivityResultContracts
import androidx.compose.foundation.layout.*
import androidx.compose.foundation.text.KeyboardActions
import androidx.compose.foundation.text.KeyboardOptions
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.filled.Mic
import androidx.compose.material.icons.filled.PhotoCamera
import androidx.compose.material.icons.filled.Send
import androidx.compose.material3.*
import androidx.compose.runtime.*
import com.alafia.android.views.components.rememberCameraCapture
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.text.input.ImeAction
import androidx.compose.ui.text.style.TextAlign
import androidx.compose.ui.unit.dp
import androidx.lifecycle.ViewModel
import androidx.lifecycle.viewModelScope
import androidx.lifecycle.viewmodel.compose.viewModel
import androidx.navigation.NavHostController
import com.alafia.android.api.ApiClient
import com.alafia.android.schemas.AIRouteRequest
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.launch
import kotlinx.coroutines.withContext
import okhttp3.MediaType.Companion.toMediaTypeOrNull
import okhttp3.MultipartBody
import okhttp3.RequestBody.Companion.toRequestBody

/**
 * Prompt Hub (Basis: "Mobile starts with a Prompt Page"). Text, voice, and camera
 * all resolve to the matching existing screen — parity with the web hub.
 *  - text/voice  -> POST ai/route -> navigate
 *  - camera      -> POST ai/vision -> Nutrition (if food found) or Image AI
 */

// Web route (from /ai/route) -> Android NavHost destination. Screens not yet on
// mobile fall back to the closest available one.
private val WEB_TO_ANDROID_ROUTE = mapOf(
    "/nutrition" to "nutrition",
    "/medications" to "medications",
    "/fitness" to "fitness",
    "/elimination" to "elimination",
    "/journal" to "mood",
    "/lifestyle" to "lifestyle",
    "/symptoms" to "mental-health",
    "/sleep" to "lifestyle",
    "/labs" to "labs",
    "/insights" to "chart-dashboard",
    "/capture" to "image-ai",
    "/ai" to "ai-chat",
)

class PromptViewModel : ViewModel() {
    var input by mutableStateOf("")
    var status by mutableStateOf("")
    var busy by mutableStateOf(false)

    /** Classify the prompt text, then invoke [onNavigate] with the Android route. */
    fun route(onNavigate: (String) -> Unit) {
        val text = input.trim()
        if (text.isEmpty() || busy) return
        busy = true
        status = "Understanding…"
        viewModelScope.launch {
            try {
                val res = ApiClient.getApiService().routePrompt(AIRouteRequest(text = text))
                status = res.assistantMessage
                onNavigate(WEB_TO_ANDROID_ROUTE[res.route] ?: "ai-chat")
            } catch (e: Exception) {
                status = "Couldn't understand that. Try the AI assistant."
            } finally {
                busy = false
            }
        }
    }

    /** A voice transcript behaves exactly like typed text. */
    fun submitTranscript(text: String, onNavigate: (String) -> Unit) {
        input = text
        route(onNavigate)
    }

    /** Upload a photo to /ai/vision; route to Nutrition if food is detected. */
    fun analyzeImage(resolver: ContentResolver, uri: Uri, onNavigate: (String) -> Unit) {
        if (busy) return
        busy = true
        status = "Looking at your photo…"
        viewModelScope.launch {
            try {
                val bytes = withContext(Dispatchers.IO) {
                    resolver.openInputStream(uri)?.use { it.readBytes() }
                } ?: throw IllegalStateException("Could not read image")
                val body = bytes.toRequestBody("image/*".toMediaTypeOrNull())
                val part = MultipartBody.Part.createFormData("file", "image.jpg", body)
                val res = ApiClient.getApiService().routeVision(part)
                if (!res.items.isNullOrEmpty()) onNavigate("nutrition") else onNavigate("image-ai")
            } catch (e: Exception) {
                status = "Image AI unavailable — opening Image AI."
                onNavigate("image-ai")
            } finally {
                busy = false
            }
        }
    }
}

@Composable
fun PromptScreen(
    navController: NavHostController,
    vm: PromptViewModel = viewModel(),
) {
    val context = LocalContext.current

    val voiceLauncher = rememberLauncherForActivityResult(
        ActivityResultContracts.StartActivityForResult()
    ) { result ->
        val spoken = result.data
            ?.getStringArrayListExtra(RecognizerIntent.EXTRA_RESULTS)
            ?.firstOrNull()
        if (!spoken.isNullOrBlank()) vm.submitTranscript(spoken) { navController.navigate(it) }
    }

    fun startVoice() {
        val intent = Intent(RecognizerIntent.ACTION_RECOGNIZE_SPEECH).apply {
            putExtra(RecognizerIntent.EXTRA_LANGUAGE_MODEL, RecognizerIntent.LANGUAGE_MODEL_FREE_FORM)
            putExtra(RecognizerIntent.EXTRA_PROMPT, "Tell ALAFIA what you ate, took, or how you feel")
        }
        try {
            voiceLauncher.launch(intent)
        } catch (e: Exception) {
            vm.status = "Voice input isn't available on this device."
        }
    }

    val imagePicker = rememberCameraCapture { uri ->
        vm.analyzeImage(context.contentResolver, uri) { navController.navigate(it) }
    }

    Column(
        modifier = Modifier
            .fillMaxSize()
            .padding(24.dp),
        horizontalAlignment = Alignment.CenterHorizontally,
        verticalArrangement = Arrangement.Center,
    ) {
        Text(
            "How are you doing today?",
            style = MaterialTheme.typography.headlineSmall,
            textAlign = TextAlign.Center,
        )
        Spacer(Modifier.height(6.dp))
        Text(
            "Type, speak, or snap a photo — ALAFIA will take you to the right place.",
            style = MaterialTheme.typography.bodyMedium,
            color = MaterialTheme.colorScheme.onSurfaceVariant,
            textAlign = TextAlign.Center,
        )
        Spacer(Modifier.height(20.dp))

        Row(verticalAlignment = Alignment.CenterVertically) {
            IconButton(onClick = { startVoice() }, enabled = !vm.busy) {
                Icon(Icons.Default.Mic, contentDescription = "Speak")
            }
            IconButton(onClick = { imagePicker.capture() }, enabled = !vm.busy) {
                Icon(Icons.Default.PhotoCamera, contentDescription = "Photo")
            }
            OutlinedTextField(
                value = vm.input,
                onValueChange = { vm.input = it },
                modifier = Modifier.weight(1f),
                placeholder = { Text("e.g. I ate jollof rice and took my 10mg lisinopril") },
                enabled = !vm.busy,
                singleLine = true,
                keyboardOptions = KeyboardOptions(imeAction = ImeAction.Send),
                keyboardActions = KeyboardActions(onSend = { vm.route { navController.navigate(it) } }),
                trailingIcon = {
                    if (vm.busy) {
                        CircularProgressIndicator(Modifier.size(22.dp), strokeWidth = 2.dp)
                    } else {
                        IconButton(onClick = { vm.route { navController.navigate(it) } }) {
                            Icon(Icons.Default.Send, contentDescription = "Send")
                        }
                    }
                },
            )
        }

        if (vm.status.isNotEmpty()) {
            Spacer(Modifier.height(12.dp))
            Text(
                vm.status,
                style = MaterialTheme.typography.bodySmall,
                color = MaterialTheme.colorScheme.onSurfaceVariant,
                textAlign = TextAlign.Center,
            )
        }
    }
}
