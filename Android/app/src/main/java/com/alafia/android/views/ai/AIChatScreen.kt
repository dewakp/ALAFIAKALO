package com.alafia.android.views.ai
import com.alafia.android.util.ErrorUtil

import android.widget.Toast
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
    val context = LocalContext.current
    val scope = rememberCoroutineScope()
    val listState = rememberLazyListState()

    // Persona state
    var personas by remember { mutableStateOf<List<AIPersona>>(emptyList()) }
    var selectedPersona by remember { mutableStateOf<AIPersona?>(null) }
    var showPersonaPicker by remember { mutableStateOf(true) }

    // Load personas on first composition
    LaunchedEffect(Unit) {
        try {
            personas = ApiClient.getApiService().getAIPersonas()
        } catch (_: Exception) {
            // Fallback personas if API unavailable
            personas = listOf(
                AIPersona("babalawo", "Babalawo", "Yoruba \u00b7 Nigeria", "africa", "\u1eb8 k\u00fa \u00e0\u00e1r\u1ecd\u0300", "Your personal health guide."),
                AIPersona("dibia", "Dibia", "Igbo \u00b7 Nigeria", "africa", "Nn\u1ecd\u1ecd", "Your personal health guide."),
                AIPersona("boka", "Boka", "Hausa \u00b7 Nigeria", "africa", "Sannu", "Your personal health guide."),
                AIPersona("sage", "Sage", "English \u00b7 UK / Ireland", "europe", "Welcome", "Your personal health guide."),
                AIPersona("medicine_keeper", "Medicine Keeper", "Native American \u00b7 United States / Canada", "north_america", "Aho", "Your personal health guide.")
            )
        }
    }

    LaunchedEffect(messages.size) {
        if (messages.isNotEmpty()) {
            listState.animateScrollToItem(messages.size - 1)
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
                                    Text(
                                        "Thinking...",
                                        modifier = Modifier.padding(horizontal = 16.dp, vertical = 10.dp),
                                        style = MaterialTheme.typography.bodyMedium,
                                        color = MaterialTheme.colorScheme.onSurfaceVariant
                                    )
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
                    Spacer(Modifier.width(8.dp))
                    FilledIconButton(
                        onClick = {
                            if (inputText.isNotBlank() && !isTyping && selectedPersona != null) {
                                val userMsg = inputText.trim()
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
                                                            val chunk = runCatching {
                                                                @Suppress("UNCHECKED_CAST")
                                                                (Gson().fromJson(payload, Map::class.java)["content"] as? String) ?: ""
                                                            }.getOrDefault("")
                                                            if (chunk.isNotEmpty()) {
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
                                }
                            }
                        },
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
                    onSelect = { persona ->
                        selectedPersona = persona
                        showPersonaPicker = false
                        messages = listOf(
                            UIChatMessage("assistant", "Welcome! I'm ${persona.title} — think of me as your personal wellness guide. What's on your mind?")
                        )
                    },
                    onDismiss = { if (selectedPersona != null) showPersonaPicker = false }
                )
            }
        }
    }
}

// ── Region labels ──────────────────────────────────────────────────
private val REGION_LABELS = mapOf(
    "africa" to "🌍 Africa",
    "middle_east" to "🕌 Middle East",
    "south_asia" to "🕉 South Asia",
    "europe" to "🏰 Europe",
    "north_america" to "🗽 North America"
)
private val REGION_ORDER = listOf("africa", "middle_east", "south_asia", "europe", "north_america")

@OptIn(ExperimentalMaterial3Api::class)
@Composable
private fun PersonaPickerDialog(
    personas: List<AIPersona>,
    selectedPersona: AIPersona?,
    onSelect: (AIPersona) -> Unit,
    onDismiss: () -> Unit
) {
    val grouped = personas.groupBy { it.region }

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
                        "Pick the name you'd like your health assistant to go by",
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

                        item {
                            Text(
                                REGION_LABELS[region] ?: region,
                                style = MaterialTheme.typography.titleSmall,
                                fontWeight = FontWeight.Bold,
                                color = MaterialTheme.colorScheme.primary,
                                modifier = Modifier.padding(top = 12.dp, bottom = 4.dp)
                            )
                        }

                        items(regionPersonas) { persona ->
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
