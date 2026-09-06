package com.alafia.android.views.ai
import com.alafia.android.util.ErrorUtil

import android.app.Activity
import android.content.Intent
import android.speech.RecognizerIntent
import android.widget.Toast
import androidx.activity.compose.rememberLauncherForActivityResult
import androidx.activity.result.contract.ActivityResultContracts
import androidx.compose.animation.core.LinearEasing
import androidx.compose.animation.core.RepeatMode
import androidx.compose.animation.core.animateFloat
import androidx.compose.animation.core.infiniteRepeatable
import androidx.compose.animation.core.rememberInfiniteTransition
import androidx.compose.animation.core.tween
import androidx.compose.foundation.background
import androidx.compose.foundation.clickable
import androidx.compose.foundation.shape.CircleShape
import androidx.compose.ui.draw.alpha
import androidx.compose.foundation.layout.*
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.lazy.items
import androidx.compose.foundation.lazy.rememberLazyListState
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.filled.*
import androidx.compose.material3.*
import androidx.compose.runtime.*
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.text.style.TextAlign
import androidx.compose.ui.unit.dp
import com.google.gson.Gson
import com.alafia.android.api.ApiClient
import com.alafia.android.api.KeychainHelper
import com.alafia.android.schemas.AIPersona
import com.alafia.android.schemas.AIRequest
import com.alafia.android.schemas.ChatMessage
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.launch
import kotlinx.coroutines.withContext
import okhttp3.MediaType.Companion.toMediaType
import okhttp3.Request
import okhttp3.RequestBody.Companion.toRequestBody
import androidx.navigation.NavHostController

data class UIChatMessage(
    val role: String,
    val content: String
)

@OptIn(ExperimentalMaterial3Api::class)
@Composable
fun AIChatScreen(navController: NavHostController) {
    var messages by remember { mutableStateOf<List<UIChatMessage>>(emptyList()) }
    var inputText by remember { mutableStateOf("") }
    var isTyping by remember { mutableStateOf(false) }
    // What the server reports it is doing. The tool rounds take tens of seconds
    // and cannot stream, so this carries the wait instead of a static word.
    // Every value is REPORTED by the backend — never a guessed sequence.
    var chatStatus by remember { mutableStateOf<ChatStatusStep?>(null) }
    val context = LocalContext.current
    val scope = rememberCoroutineScope()
    val listState = rememberLazyListState()

    // Persona state
    var personas by remember { mutableStateOf<List<AIPersona>>(emptyList()) }
    var selectedPersona by remember { mutableStateOf<AIPersona?>(null) }
    var showPersonaPicker by remember { mutableStateOf(false) }   // opt-in; default to device locale

    // Select a persona and seed its greeting (shared by the picker + the locale default).
    fun choosePersona(p: AIPersona) {
        selectedPersona = p
        showPersonaPicker = false
        // Opening line comes from the backend (p.opening) so the AI's voice is
        // server-controlled; only fall back to a neutral generic if absent.
        messages = listOf(
            UIChatMessage("assistant", p.opening ?: "Welcome \u2014 how can I help with your health today?")
        )
    }

    // Load personas on first composition
    LaunchedEffect(Unit) {
        try {
            personas = ApiClient.getApiService().getAIPersonas()
        } catch (_: Exception) {
            // The persona roster is backend-owned (AI stays server-driven \u2014 no
            // named guides baked into the app). If the fetch fails, fall back to a
            // single neutral assistant so chat still works offline.
            personas = listOf(
                AIPersona("assistant", "Assistant", "", "specialist", "Welcome", "Your personal health guide.")
            )
        }
        // Default to a device-locale guide instead of forcing the picker.
        if (selectedPersona == null && personas.isNotEmpty()) {
            val code = java.util.Locale.getDefault().language
            val langEn = java.util.Locale(code, "").getDisplayLanguage(java.util.Locale.ENGLISH)
            val default = personas.firstOrNull { langEn.isNotEmpty() && it.origin.startsWith(langEn, ignoreCase = true) }
                ?: personas.firstOrNull { it.key == "general_practitioner" }
                ?: personas.firstOrNull { it.region == "specialist" }
                ?: personas.firstOrNull()
            default?.let { choosePersona(it) }
        }
    }

    LaunchedEffect(messages.size) {
        if (messages.isNotEmpty()) {
            listState.animateScrollToItem(messages.size - 1)
        }
    }

    // Stream a user message to the agent — shared by the send button and voice input.
    fun send(userMsg: String) {
        if (userMsg.isBlank() || isTyping || selectedPersona == null) return
        // Snapshot history before adding the new user message
        val history = messages.map { ChatMessage(it.role, it.content) }
        inputText = ""
        messages = messages + UIChatMessage("user", userMsg)
        isTyping = true

        scope.launch {
            // Add placeholder for streaming tokens
            messages = messages + UIChatMessage("assistant", "")
            val placeholderIdx = messages.size - 1
            val acc = StringBuilder()

            try {
                val requestBody = AIRequest(
                    query = userMsg,
                    messages = history,
                    persona = selectedPersona?.key
                )
                val json = Gson().toJson(requestBody)
                val mediaType = "application/json".toMediaType()
                val token = KeychainHelper.getToken(context)
                val okRequest = Request.Builder()
                    .url("${ApiClient.BASE_URL}ai/chat/stream")
                    .post(json.toRequestBody(mediaType))
                    .apply { token?.let { addHeader("Authorization", "Bearer $it") } }
                    .build()

                withContext(Dispatchers.IO) {
                    ApiClient.getOkHttpClient()
                        .newCall(okRequest)
                        .execute()
                        .use { response ->
                            val source = response.body?.source() ?: return@use
                            while (!source.exhausted()) {
                                val line = source.readUtf8Line() ?: break
                                if (line.startsWith("data: ")) {
                                    val payload = line.removePrefix("data: ")
                                    if (payload == "[DONE]") break
                                    val frame = runCatching {
                                        Gson().fromJson(payload, Map::class.java)
                                    }.getOrNull()
                                    // A progress frame carries a nested object;
                                    // reading it as a String (as this did) yields
                                    // null and drops it silently.
                                    (frame?.get("status") as? Map<*, *>)?.let { st ->
                                        (st["label"] as? String)?.let { label ->
                                            val step = ChatStatusStep(label, st["detail"] as? String)
                                            withContext(Dispatchers.Main) { chatStatus = step }
                                        }
                                    }
                                    // That text came from a round that turned out
                                    // to be a data fetch, not the answer — models
                                    // narrate before calling a tool. Drop exactly
                                    // what the server took back, or the preamble
                                    // is spliced onto the front of the answer.
                                    (frame?.get("retract") as? Number)?.let { n ->
                                        val drop = n.toInt()
                                        if (drop > 0) {
                                            val keep = (acc.length - drop).coerceAtLeast(0)
                                            acc.setLength(keep)
                                            val snap = acc.toString()
                                            withContext(Dispatchers.Main) {
                                                val updated = messages.toMutableList()
                                                if (placeholderIdx < updated.size) {
                                                    updated[placeholderIdx] = UIChatMessage("assistant", snap)
                                                    messages = updated
                                                }
                                            }
                                        }
                                    }
                                    val chunk = (frame?.get("content") as? String) ?: ""
                                    if (chunk.isNotEmpty()) {
                                        withContext(Dispatchers.Main) { chatStatus = null }
                                        acc.append(chunk)
                                        val snap = acc.toString()
                                        withContext(Dispatchers.Main) {
                                            val updated = messages.toMutableList()
                                            if (placeholderIdx < updated.size) {
                                                updated[placeholderIdx] = UIChatMessage("assistant", snap)
                                                messages = updated
                                            }
                                        }
                                    }
                                }
                            }
                        }
                }
            } catch (e: Exception) {
                val updated = messages.toMutableList()
                if (placeholderIdx < updated.size) {
                    updated[placeholderIdx] = UIChatMessage("assistant", "Sorry, I couldn't process your request. Please try again.")
                    messages = updated
                }
                Toast.makeText(context, ErrorUtil.userMessage(e), Toast.LENGTH_SHORT).show()
            }
            isTyping = false
            chatStatus = null
        }
    }

    // Voice input: the system speech recognizer returns a final transcript that is
    // sent straight to the agent (parity with the web chat's mic). Uses the out-of-
    // process RecognizerIntent, so no RECORD_AUDIO permission is needed here.
    val speechLauncher = rememberLauncherForActivityResult(
        ActivityResultContracts.StartActivityForResult()
    ) { result ->
        if (result.resultCode == Activity.RESULT_OK) {
            val spoken = result.data
                ?.getStringArrayListExtra(RecognizerIntent.EXTRA_RESULTS)
                ?.firstOrNull()
                ?.trim()
                .orEmpty()
            if (spoken.isNotBlank()) send(spoken)
        }
    }

    fun startVoice() {
        val intent = Intent(RecognizerIntent.ACTION_RECOGNIZE_SPEECH).apply {
            putExtra(RecognizerIntent.EXTRA_LANGUAGE_MODEL, RecognizerIntent.LANGUAGE_MODEL_FREE_FORM)
            putExtra(RecognizerIntent.EXTRA_PROMPT, "Speak your question")
        }
        try {
            speechLauncher.launch(intent)
        } catch (_: Exception) {
            Toast.makeText(context, "Voice input isn't available on this device", Toast.LENGTH_SHORT).show()
        }
    }

    Scaffold(
        topBar = {
            TopAppBar(
                title = {
                    Column {
                        Text("AI Health Assistant")
                        if (selectedPersona != null) {
                            Text(
                                "${selectedPersona!!.title} (${selectedPersona!!.origin})",
                                style = MaterialTheme.typography.bodySmall,
                                color = MaterialTheme.colorScheme.onPrimaryContainer.copy(alpha = 0.7f)
                            )
                        }
                    }
                },
                navigationIcon = {
                    IconButton(onClick = { navController.popBackStack() }) {
                        Icon(Icons.Default.ArrowBack, contentDescription = "Back")
                    }
                },
                actions = {
                    IconButton(onClick = { showPersonaPicker = true }) {
                        Icon(Icons.Default.Face, "Change Persona")
                    }
                },
                colors = TopAppBarDefaults.topAppBarColors(
                    containerColor = MaterialTheme.colorScheme.primaryContainer
                )
            )
        }
    ) { padding ->
        Box(
            modifier = Modifier
                .fillMaxSize()
                .padding(padding)
        ) {
            Column(modifier = Modifier.fillMaxSize()) {
                // Messages
                LazyColumn(
                    state = listState,
                    modifier = Modifier
                        .weight(1f)
                        .fillMaxWidth()
                        .padding(horizontal = 16.dp),
                    verticalArrangement = Arrangement.spacedBy(8.dp),
                    contentPadding = PaddingValues(vertical = 12.dp)
                ) {
                    items(messages) { msg ->
                        ChatBubble(msg)
                    }
                    if (isTyping) {
                        item {
                            Row(
                                modifier = Modifier.fillMaxWidth(),
                                horizontalArrangement = Arrangement.Start
                            ) {
                                Surface(
                                    color = MaterialTheme.colorScheme.surfaceVariant,
                                    shape = RoundedCornerShape(16.dp)
                                ) {
                                    ChatStatusRow(chatStatus)
                                }
                            }
                        }
                    }
                }

                // Input
                HorizontalDivider()
                Row(
                    modifier = Modifier
                        .fillMaxWidth()
                        .padding(12.dp),
                    verticalAlignment = Alignment.CenterVertically
                ) {
                    OutlinedTextField(
                        value = inputText,
                        onValueChange = { inputText = it },
                        modifier = Modifier.weight(1f),
                        placeholder = { Text("Ask about your health...") },
                        shape = RoundedCornerShape(24.dp),
                        enabled = !isTyping && selectedPersona != null
                    )
                    Spacer(Modifier.width(4.dp))
                    IconButton(
                        onClick = { startVoice() },
                        enabled = !isTyping && selectedPersona != null
                    ) {
                        Icon(Icons.Default.Mic, contentDescription = "Speak your question")
                    }
                    Spacer(Modifier.width(4.dp))
                    FilledIconButton(
                        onClick = { send(inputText.trim()) },
                        enabled = inputText.isNotBlank() && !isTyping && selectedPersona != null
                    ) {
                        Icon(Icons.Default.Send, "Send")
                    }
                }
            }

            // ── Persona Picker Overlay ──────────────────────────────────
            if (showPersonaPicker && personas.isNotEmpty()) {
                PersonaPickerDialog(
                    personas = personas,
                    selectedPersona = selectedPersona,
                    onSelect = { persona -> choosePersona(persona) },
                    onDismiss = { showPersonaPicker = false }
                )
            }
        }
    }
}

// ── Region labels ──────────────────────────────────────────────────
private val REGION_LABELS = mapOf(
    "specialist" to "🏥 Specialist Agents",
    "africa" to "🌍 Africa",
    "middle_east" to "🕌 Middle East",
    "south_asia" to "🕉 South Asia",
    "europe" to "🏰 Europe",
    "north_america" to "🗽 North America"
)
private val REGION_ORDER = listOf("specialist", "africa", "middle_east", "south_asia", "europe", "north_america")

@OptIn(ExperimentalMaterial3Api::class)
@Composable
private fun PersonaPickerDialog(
    personas: List<AIPersona>,
    selectedPersona: AIPersona?,
    onSelect: (AIPersona) -> Unit,
    onDismiss: () -> Unit
) {
    val grouped = personas.groupBy { it.region }
    var expanded by remember { mutableStateOf(setOf("specialist")) }   // roll up per region

    AlertDialog(onDismissRequest = onDismiss) {
        Surface(
            shape = RoundedCornerShape(24.dp),
            color = MaterialTheme.colorScheme.surface,
            tonalElevation = 6.dp,
            modifier = Modifier
                .fillMaxWidth()
                .fillMaxHeight(0.85f)
        ) {
            Column {
                // Header
                Column(modifier = Modifier.padding(24.dp, 20.dp, 24.dp, 8.dp)) {
                    Text(
                        "Choose Your Guide",
                        style = MaterialTheme.typography.headlineSmall,
                        fontWeight = FontWeight.Bold
                    )
                    Spacer(Modifier.height(4.dp))
                    Text(
                        "Optional — close to keep your device-language guide, or pick another.",
                        style = MaterialTheme.typography.bodyMedium,
                        color = MaterialTheme.colorScheme.onSurfaceVariant
                    )
                }

                HorizontalDivider()

                // Scrollable list grouped by region
                LazyColumn(
                    modifier = Modifier.weight(1f),
                    contentPadding = PaddingValues(horizontal = 16.dp, vertical = 8.dp),
                    verticalArrangement = Arrangement.spacedBy(6.dp)
                ) {
                    REGION_ORDER.forEach { region ->
                        val regionPersonas = grouped[region] ?: return@forEach
                        val isExpanded = expanded.contains(region)

                        item {
                            Row(
                                modifier = Modifier
                                    .fillMaxWidth()
                                    .clickable { expanded = if (isExpanded) expanded - region else expanded + region }
                                    .padding(top = 12.dp, bottom = 4.dp),
                                verticalAlignment = Alignment.CenterVertically
                            ) {
                                Icon(
                                    if (isExpanded) Icons.Default.ExpandMore else Icons.Default.ChevronRight,
                                    contentDescription = null,
                                    modifier = Modifier.size(18.dp),
                                    tint = MaterialTheme.colorScheme.primary
                                )
                                Spacer(Modifier.width(4.dp))
                                Text(
                                    REGION_LABELS[region] ?: region,
                                    style = MaterialTheme.typography.titleSmall,
                                    fontWeight = FontWeight.Bold,
                                    color = MaterialTheme.colorScheme.primary,
                                    modifier = Modifier.weight(1f)
                                )
                                Text(
                                    "${regionPersonas.size}",
                                    style = MaterialTheme.typography.labelSmall,
                                    color = MaterialTheme.colorScheme.onSurfaceVariant
                                )
                            }
                        }

                        if (isExpanded) items(regionPersonas) { persona ->
                            val isSelected = selectedPersona?.key == persona.key
                            OutlinedCard(
                                onClick = { onSelect(persona) },
                                colors = CardDefaults.outlinedCardColors(
                                    containerColor = if (isSelected)
                                        MaterialTheme.colorScheme.primaryContainer
                                    else MaterialTheme.colorScheme.surface
                                ),
                                border = if (isSelected) androidx.compose.foundation.BorderStroke(
                                    2.dp, MaterialTheme.colorScheme.primary
                                ) else CardDefaults.outlinedCardBorder()
                            ) {
                                Row(
                                    modifier = Modifier
                                        .fillMaxWidth()
                                        .padding(14.dp),
                                    verticalAlignment = Alignment.CenterVertically,
                                    horizontalArrangement = Arrangement.spacedBy(10.dp)
                                ) {
                                    Column(modifier = Modifier.weight(1f)) {
                                        Text(
                                            persona.title,
                                            style = MaterialTheme.typography.titleMedium,
                                            fontWeight = FontWeight.Bold
                                        )
                                        Text(
                                            persona.origin,
                                            style = MaterialTheme.typography.bodySmall,
                                            color = MaterialTheme.colorScheme.onSurfaceVariant
                                        )
                                    }
                                    if (isSelected) {
                                        Icon(
                                            Icons.Default.Check,
                                            contentDescription = "Selected",
                                            tint = MaterialTheme.colorScheme.primary
                                        )
                                    }
                                }
                            }
                        }
                    }
                }
                HorizontalDivider()
                TextButton(
                    onClick = onDismiss,
                    modifier = Modifier
                        .align(Alignment.End)
                        .padding(horizontal = 12.dp, vertical = 4.dp)
                ) { Text("Close") }
            }
        }
    }
}

@Composable
private fun ChatBubble(msg: UIChatMessage) {
    val isUser = msg.role == "user"

    Row(
        modifier = Modifier.fillMaxWidth(),
        horizontalArrangement = if (isUser) Arrangement.End else Arrangement.Start
    ) {
        Surface(
            color = if (isUser) MaterialTheme.colorScheme.primary else MaterialTheme.colorScheme.surfaceVariant,
            shape = RoundedCornerShape(
                topStart = 16.dp,
                topEnd = 16.dp,
                bottomStart = if (isUser) 16.dp else 4.dp,
                bottomEnd = if (isUser) 4.dp else 16.dp
            ),
            modifier = Modifier.widthIn(max = 300.dp)
        ) {
            Text(
                msg.content,
                modifier = Modifier.padding(horizontal = 14.dp, vertical = 10.dp),
                color = if (isUser) MaterialTheme.colorScheme.onPrimary else MaterialTheme.colorScheme.onSurface,
                style = MaterialTheme.typography.bodyMedium
            )
        }
    }
}


/** One reported step of the assistant's work, as shown to the patient. */
data class ChatStatusStep(val label: String, val detail: String?)

/**
 * Animated "what I'm doing" row.
 *
 * The tool rounds take tens of seconds and cannot stream — the model has to read
 * each result before it knows what to ask next — so the answer arrives at the
 * end, all at once. This used to be the static word "Thinking...", which cannot
 * tell a working request from a hung one.
 *
 * The label comes from the server, so it never claims a step that did not run,
 * and a new tool does not need an app release to get a name. Before the first
 * frame lands there is still something true to say: the request is open.
 */
@Composable
private fun ChatStatusRow(step: ChatStatusStep?) {
    val transition = rememberInfiniteTransition(label = "chat-status")
    Row(
        modifier = Modifier.padding(horizontal = 16.dp, vertical = 10.dp),
        verticalAlignment = Alignment.CenterVertically,
        horizontalArrangement = Arrangement.spacedBy(8.dp)
    ) {
        Row(horizontalArrangement = Arrangement.spacedBy(3.dp)) {
            repeat(3) { i ->
                val alpha by transition.animateFloat(
                    initialValue = 0.35f,
                    targetValue = 1f,
                    animationSpec = infiniteRepeatable(
                        animation = tween(600, delayMillis = i * 150, easing = LinearEasing),
                        repeatMode = RepeatMode.Reverse
                    ),
                    label = "dot$i"
                )
                Box(
                    modifier = Modifier
                        .size(5.dp)
                        .alpha(alpha)
                        .background(MaterialTheme.colorScheme.onSurfaceVariant, CircleShape)
                )
            }
        }
        val text = step?.let { s -> s.detail?.let { "${s.label} — $it" } ?: s.label }
            ?: "Querying AI…"
        Text(
            text,
            style = MaterialTheme.typography.bodyMedium,
            color = MaterialTheme.colorScheme.onSurfaceVariant
        )
    }
}
