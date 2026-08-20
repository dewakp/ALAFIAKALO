package com.alafia.android.views.messaging

import androidx.compose.foundation.background
import androidx.compose.foundation.clickable
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.verticalScroll
import androidx.compose.foundation.layout.*
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.lazy.LazyRow
import androidx.compose.foundation.lazy.items
import androidx.compose.foundation.lazy.rememberLazyListState
import androidx.compose.foundation.shape.CircleShape
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.filled.*
import androidx.compose.material3.*
import androidx.compose.runtime.*
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.clip
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.text.style.TextOverflow
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import com.alafia.android.api.ApiClient
import com.alafia.android.models.*
import com.alafia.android.schemas.*
import kotlinx.coroutines.delay
import kotlinx.coroutines.launch
import java.time.LocalDateTime
import java.time.format.DateTimeFormatter
import androidx.navigation.NavHostController

@OptIn(ExperimentalMaterial3Api::class)
@Composable
fun MessagingScreen(navController: NavHostController) {
    val scope = rememberCoroutineScope()

    // State
    var currentView by remember { mutableStateOf("hub") } // hub, conversations, chat, feed, postDetail
    var conversations by remember { mutableStateOf<List<Conversation>>(emptyList()) }
    var posts by remember { mutableStateOf<List<CommunityPost>>(emptyList()) }
    var messages by remember { mutableStateOf<List<ConversationMessage>>(emptyList()) }
    var replies by remember { mutableStateOf<List<PostReply>>(emptyList()) }
    var selectedConv by remember { mutableStateOf<Conversation?>(null) }
    var selectedPost by remember { mutableStateOf<CommunityPost?>(null) }
    var convFilter by remember { mutableStateOf<String?>(null) }
    var createError by remember { mutableStateOf<String?>(null) }
    var feedTopic by remember { mutableStateOf<String?>(null) }
    var isLoading by remember { mutableStateOf(false) }
    var errorMessage by remember { mutableStateOf<String?>(null) }
    var showCreateConv by remember { mutableStateOf(false) }
    var showCreatePost by remember { mutableStateOf(false) }

    // Load functions
    fun loadConversations() {
        scope.launch {
            isLoading = true
            try {
                conversations = ApiClient.getApiService().getConversations(convFilter)
            } catch (_: Exception) { errorMessage = "Failed to load conversations" }
            isLoading = false
        }
    }

    fun loadFeed() {
        scope.launch {
            isLoading = true
            try {
                posts = ApiClient.getApiService().getFeed(feedTopic)
            } catch (_: Exception) { errorMessage = "Failed to load feed" }
            isLoading = false
        }
    }

    fun loadMessages(convId: Int) {
        scope.launch {
            try {
                messages = ApiClient.getApiService().getMessages(convId)
            } catch (_: Exception) { errorMessage = "Failed to load messages" }
        }
    }

    fun loadReplies(postId: Int) {
        scope.launch {
            try {
                replies = ApiClient.getApiService().getReplies(postId)
            } catch (_: Exception) { errorMessage = "Failed to load replies" }
        }
    }

    // Snackbar for errors
    LaunchedEffect(errorMessage) {
        if (errorMessage != null) {
            kotlinx.coroutines.delay(3000)
            errorMessage = null
        }
    }

    Scaffold(
        topBar = {
            TopAppBar(
                title = {
                    Text(when (currentView) {
                        "hub" -> "Messaging"
                        "conversations" -> "Conversations"
                        "chat" -> selectedConv?.displayTitle ?: "Chat"
                        "feed" -> "Community Feed"
                        "postDetail" -> "Post"
                        else -> "Messaging"
                    })
                },
                navigationIcon = {
                    if (currentView == "hub") {
                        IconButton(onClick = { navController.popBackStack() }) {
                            Icon(Icons.Default.ArrowBack, contentDescription = "Back")
                        }
                    } else if (currentView != "hub") {
                        IconButton(onClick = {
                            currentView = when (currentView) {
                                "chat" -> "conversations"
                                "postDetail" -> "feed"
                                else -> "hub"
                            }
                        }) {
                            Icon(Icons.Default.ArrowBack, "Back")
                        }
                    }
                },
                actions = {
                    if (currentView == "hub" || currentView == "conversations") {
                        IconButton(onClick = { showCreateConv = true }) {
                            Icon(Icons.Default.Add, "New Conversation")
                        }
                    }
                    if (currentView == "hub" || currentView == "feed") {
                        IconButton(onClick = { showCreatePost = true }) {
                            Icon(Icons.Default.Edit, "New Post")
                        }
                    }
                }
            )
        }
    ) { padding ->
        Column(modifier = Modifier.padding(padding).fillMaxSize()) {
            // Error banner
            errorMessage?.let { msg ->
                Card(
                    modifier = Modifier
                        .fillMaxWidth()
                        .padding(horizontal = 16.dp, vertical = 4.dp),
                    colors = CardDefaults.cardColors(containerColor = MaterialTheme.colorScheme.errorContainer)
                ) {
                    Text(
                        msg,
                        modifier = Modifier.padding(12.dp),
                        color = MaterialTheme.colorScheme.onErrorContainer,
                        style = MaterialTheme.typography.bodySmall
                    )
                }
            }

            when (currentView) {
                "hub" -> HubView(
                    onNavigate = { dest, filter ->
                        convFilter = filter
                        currentView = dest
                        if (dest == "conversations") loadConversations()
                        if (dest == "feed") loadFeed()
                    }
                )
                "conversations" -> ConversationsView(
                    conversations = conversations,
                    convFilter = convFilter,
                    isLoading = isLoading,
                    onFilterChange = { convFilter = it; loadConversations() },
                    onSelect = { conv ->
                        selectedConv = conv
                        currentView = "chat"
                        loadMessages(conv.id)
                        scope.launch {
                            try { ApiClient.getApiService().markConversationRead(conv.id) }
                            catch (_: Exception) {}
                        }
                    },
                    onCreateNew = { showCreateConv = true }
                )
                "chat" -> selectedConv?.let { conv ->
                    ChatView(
                        conversation = conv,
                        messages = messages,
                        onSend = { content ->
                            scope.launch {
                                try {
                                    ApiClient.getApiService().sendMessage(conv.id, SendMessageRequest(content = content))
                                    loadMessages(conv.id)
                                } catch (_: Exception) { errorMessage = "Failed to send message" }
                            }
                        }
                    )
                }
                "feed" -> FeedView(
                    posts = posts,
                    feedTopic = feedTopic,
                    isLoading = isLoading,
                    onTopicChange = { feedTopic = it; loadFeed() },
                    onSelectPost = { post ->
                        selectedPost = post
                        currentView = "postDetail"
                        loadReplies(post.id)
                    },
                    onLike = { post ->
                        scope.launch {
                            try {
                                if (post.userLiked == true) {
                                    ApiClient.getApiService().unlikePost(post.id)
                                } else {
                                    ApiClient.getApiService().likePost(post.id)
                                }
                                loadFeed()
                            } catch (_: Exception) {}
                        }
                    },
                    onCreateNew = { showCreatePost = true }
                )
                "postDetail" -> selectedPost?.let { post ->
                    PostDetailView(
                        post = post,
                        replies = replies,
                        onSendReply = { content ->
                            scope.launch {
                                try {
                                    ApiClient.getApiService().createReply(post.id, CreateReplyRequest(content))
                                    loadReplies(post.id)
                                    // Refresh post for updated counts
                                    try {
                                        selectedPost = ApiClient.getApiService().getPost(post.id)
                                    } catch (_: Exception) {}
                                } catch (_: Exception) { errorMessage = "Failed to send reply" }
                            }
                        },
                        onLike = {
                            scope.launch {
                                try {
                                    if (post.userLiked == true) {
                                        ApiClient.getApiService().unlikePost(post.id)
                                    } else {
                                        ApiClient.getApiService().likePost(post.id)
                                    }
                                    try {
                                        selectedPost = ApiClient.getApiService().getPost(post.id)
                                    } catch (_: Exception) {}
                                } catch (_: Exception) {}
                            }
                        }
                    )
                }
            }
        }
    }

    // Create Conversation Sheet
    if (showCreateConv) {
        CreateConversationSheet(
            defaultType = convFilter ?: "direct",
            typeLocked = convFilter != null,
            errorMessage = createError,
            onDismiss = { showCreateConv = false; createError = null },
            onCreate = { request ->
                scope.launch {
                    try {
                        createError = null
                        val conv = ApiClient.getApiService().createConversation(request)
                        showCreateConv = false
                        selectedConv = conv
                        currentView = "chat"
                        loadMessages(conv.id)
                    } catch (e: Exception) {
                        // Shown inside the sheet, which is where the user is looking.
                        createError = e.message ?: "Could not create the conversation."
                    }
                }
            }
        )
    }

    // Create Post Sheet
    if (showCreatePost) {
        CreatePostSheet(
            onDismiss = { showCreatePost = false },
            onCreate = { request ->
                scope.launch {
                    try {
                        ApiClient.getApiService().createPost(request)
                        showCreatePost = false
                        loadFeed()
                        currentView = "feed"
                    } catch (_: Exception) { errorMessage = "Failed to create post" }
                }
            }
        )
    }
}

// ── Hub View ──

@Composable
private fun HubView(onNavigate: (String, String?) -> Unit) {
    LazyColumn(
        modifier = Modifier.fillMaxSize(),
        contentPadding = PaddingValues(16.dp),
        verticalArrangement = Arrangement.spacedBy(12.dp)
    ) {
        item {
            HubCard(
                icon = Icons.Default.Email,
                title = "Direct Messages",
                description = "Private 1-on-1 conversations",
                color = MaterialTheme.colorScheme.primary,
                onClick = { onNavigate("conversations", "direct") }
            )
        }
        item {
            HubCard(
                icon = Icons.Default.LocalHospital,
                title = "Clinical Channels",
                description = "Physician, nurse, social worker messaging",
                color = Color(0xFF4CAF50),
                onClick = { onNavigate("conversations", "clinical") }
            )
        }
        item {
            HubCard(
                icon = Icons.Default.Group,
                title = "Group Chats",
                description = "Group and care team channels",
                color = Color(0xFF9C27B0),
                onClick = { onNavigate("conversations", "group") }
            )
        }
        item {
            HubCard(
                icon = Icons.Default.Public,
                title = "Community Feed",
                description = "Public timeline — share & support",
                color = Color(0xFFFF9800),
                onClick = { onNavigate("feed", null) }
            )
        }
    }
}

@Composable
private fun HubCard(
    icon: androidx.compose.ui.graphics.vector.ImageVector,
    title: String,
    description: String,
    color: Color,
    onClick: () -> Unit
) {
    Card(
        modifier = Modifier
            .fillMaxWidth()
            .clickable(onClick = onClick),
        elevation = CardDefaults.cardElevation(defaultElevation = 2.dp)
    ) {
        Row(
            modifier = Modifier.padding(16.dp),
            verticalAlignment = Alignment.CenterVertically
        ) {
            Box(
                modifier = Modifier
                    .size(48.dp)
                    .clip(CircleShape)
                    .background(color.copy(alpha = 0.12f)),
                contentAlignment = Alignment.Center
            ) {
                Icon(icon, null, tint = color, modifier = Modifier.size(24.dp))
            }
            Spacer(Modifier.width(14.dp))
            Column(modifier = Modifier.weight(1f)) {
                Text(title, style = MaterialTheme.typography.titleSmall, fontWeight = FontWeight.SemiBold)
                Text(description, style = MaterialTheme.typography.bodySmall, color = MaterialTheme.colorScheme.onSurfaceVariant)
            }
            Icon(Icons.Default.ChevronRight, null, tint = MaterialTheme.colorScheme.onSurfaceVariant)
        }
    }
}

// ── Conversations View ──

@OptIn(ExperimentalMaterial3Api::class)
@Composable
private fun ConversationsView(
    conversations: List<Conversation>,
    convFilter: String?,
    isLoading: Boolean,
    onFilterChange: (String?) -> Unit,
    onSelect: (Conversation) -> Unit,
    onCreateNew: () -> Unit
) {
    val filters = listOf(null to "All", "direct" to "Direct", "clinical" to "Clinical", "group" to "Group", "care_team" to "Care Team")

    Column(modifier = Modifier.fillMaxSize()) {
        // Filter chips
        LazyRow(
            modifier = Modifier.padding(horizontal = 16.dp, vertical = 8.dp),
            horizontalArrangement = Arrangement.spacedBy(8.dp)
        ) {
            items(filters) { (value, label) ->
                FilterChip(
                    selected = convFilter == value,
                    onClick = { onFilterChange(value) },
                    label = { Text(label) }
                )
            }
        }

        if (isLoading) {
            Box(modifier = Modifier.fillMaxSize(), contentAlignment = Alignment.Center) {
                CircularProgressIndicator()
            }
        } else if (conversations.isEmpty()) {
            Box(modifier = Modifier.fillMaxSize(), contentAlignment = Alignment.Center) {
                Column(horizontalAlignment = Alignment.CenterHorizontally) {
                    Icon(Icons.Default.Email, null, modifier = Modifier.size(48.dp), tint = MaterialTheme.colorScheme.onSurfaceVariant)
                    Spacer(Modifier.height(8.dp))
                    Text("No conversations yet", color = MaterialTheme.colorScheme.onSurfaceVariant)
                    Spacer(Modifier.height(12.dp))
                    Button(onClick = onCreateNew) { Text("Start a Conversation") }
                }
            }
        } else {
            LazyColumn(
                modifier = Modifier.fillMaxSize(),
                contentPadding = PaddingValues(horizontal = 16.dp)
            ) {
                items(conversations) { conv ->
                    ConversationRow(conv = conv, onClick = { onSelect(conv) })
                }
            }
        }
    }
}

@Composable
private fun ConversationRow(conv: Conversation, onClick: () -> Unit) {
    val typeColor = when (conv.conversationType) {
        "direct" -> MaterialTheme.colorScheme.primary
        "clinical" -> Color(0xFF4CAF50)
        "group" -> Color(0xFF9C27B0)
        "care_team" -> Color(0xFFFF9800)
        else -> Color.Gray
    }

    Card(
        modifier = Modifier
            .fillMaxWidth()
            .padding(vertical = 4.dp)
            .clickable(onClick = onClick),
        colors = CardDefaults.cardColors(containerColor = MaterialTheme.colorScheme.surface)
    ) {
        Row(
            modifier = Modifier.padding(12.dp),
            verticalAlignment = Alignment.CenterVertically
        ) {
            Box(
                modifier = Modifier
                    .size(40.dp)
                    .clip(CircleShape)
                    .background(typeColor.copy(alpha = 0.15f)),
                contentAlignment = Alignment.Center
            ) {
                Text(
                    conv.displayTitle.take(1),
                    style = MaterialTheme.typography.titleSmall,
                    color = typeColor,
                    fontWeight = FontWeight.Bold
                )
            }
            Spacer(Modifier.width(12.dp))
            Column(modifier = Modifier.weight(1f)) {
                Row(verticalAlignment = Alignment.CenterVertically) {
                    Text(
                        conv.displayTitle,
                        style = MaterialTheme.typography.bodyMedium,
                        fontWeight = FontWeight.SemiBold,
                        maxLines = 1,
                        overflow = TextOverflow.Ellipsis,
                        modifier = Modifier.weight(1f, fill = false)
                    )
                    if (conv.isUrgent) {
                        Spacer(Modifier.width(4.dp))
                        Text("⚡", fontSize = 12.sp)
                    }
                }
                Text(
                    conv.lastMessagePreview ?: "No messages yet",
                    style = MaterialTheme.typography.bodySmall,
                    color = MaterialTheme.colorScheme.onSurfaceVariant,
                    maxLines = 1,
                    overflow = TextOverflow.Ellipsis
                )
            }
            Column(
                horizontalAlignment = Alignment.End,
                verticalArrangement = Arrangement.spacedBy(4.dp)
            ) {
                val unread = conv.unreadCount ?: 0
                if (unread > 0) {
                    Badge { Text("$unread") }
                }
                conv.lastMessageAt?.let {
                    Text(formatShortDate(it), style = MaterialTheme.typography.labelSmall, color = MaterialTheme.colorScheme.onSurfaceVariant)
                }
            }
        }
    }
}

// ── Chat View ──

@Composable
private fun ChatView(
    conversation: Conversation,
    messages: List<ConversationMessage>,
    onSend: (String) -> Unit
) {
    var messageText by remember { mutableStateOf("") }
    val listState = rememberLazyListState()
    val context = LocalContext.current
    val currentUserId = remember { com.alafia.android.api.KeychainHelper.getUserId(context)?.toIntOrNull() ?: 0 }
    val scope = rememberCoroutineScope()

    LaunchedEffect(messages.size) {
        if (messages.isNotEmpty()) {
            listState.animateScrollToItem(messages.size - 1)
        }
    }

    Column(modifier = Modifier.fillMaxSize()) {
        // Info bar
        Card(
            modifier = Modifier
                .fillMaxWidth()
                .padding(horizontal = 16.dp, vertical = 4.dp),
            colors = CardDefaults.cardColors(containerColor = MaterialTheme.colorScheme.surfaceVariant)
        ) {
            Row(
                modifier = Modifier.padding(12.dp),
                verticalAlignment = Alignment.CenterVertically
            ) {
                Column(modifier = Modifier.weight(1f)) {
                    Text(conversation.displayTitle, style = MaterialTheme.typography.titleSmall, fontWeight = FontWeight.SemiBold)
                    Text(
                        "${conversation.members?.size ?: 0} members · ${conversation.conversationType.replace("_", " ").replaceFirstChar { it.uppercase() }}",
                        style = MaterialTheme.typography.bodySmall,
                        color = MaterialTheme.colorScheme.onSurfaceVariant
                    )
                }
                if (conversation.isUrgent) {
                    AssistChip(
                        onClick = {},
                        label = { Text("URGENT", fontSize = 10.sp, fontWeight = FontWeight.Bold) },
                        colors = AssistChipDefaults.assistChipColors(containerColor = MaterialTheme.colorScheme.error, labelColor = MaterialTheme.colorScheme.onError)
                    )
                }
            }
        }

        // Messages
        LazyColumn(
            state = listState,
            modifier = Modifier
                .weight(1f)
                .fillMaxWidth()
                .padding(horizontal = 16.dp),
            verticalArrangement = Arrangement.spacedBy(4.dp),
            contentPadding = PaddingValues(vertical = 8.dp)
        ) {
            items(messages) { msg ->
                MessageBubble(msg = msg, isOwn = msg.senderId == currentUserId)
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
                value = messageText,
                onValueChange = { messageText = it },
                modifier = Modifier.weight(1f),
                placeholder = { Text("Type a message...") },
                singleLine = true,
                shape = RoundedCornerShape(24.dp)
            )
            Spacer(Modifier.width(8.dp))
            IconButton(
                onClick = {
                    if (messageText.isNotBlank()) {
                        onSend(messageText)
                        messageText = ""
                    }
                },
                enabled = messageText.isNotBlank()
            ) {
                Icon(
                    Icons.Default.Send,
                    "Send",
                    tint = if (messageText.isNotBlank()) MaterialTheme.colorScheme.primary else MaterialTheme.colorScheme.onSurfaceVariant
                )
            }
        }
    }
}

@Composable
private fun MessageBubble(msg: ConversationMessage, isOwn: Boolean) {
    if (msg.isDeleted) {
        Text(
            "Message deleted",
            style = MaterialTheme.typography.bodySmall,
            color = MaterialTheme.colorScheme.onSurfaceVariant,
            modifier = Modifier
                .fillMaxWidth()
                .padding(vertical = 4.dp),
            textAlign = androidx.compose.ui.text.style.TextAlign.Center
        )
    } else if (msg.messageType == "system") {
        Text(
            msg.content ?: "",
            style = MaterialTheme.typography.bodySmall,
            color = MaterialTheme.colorScheme.onSurfaceVariant,
            modifier = Modifier
                .fillMaxWidth()
                .padding(vertical = 4.dp),
            textAlign = androidx.compose.ui.text.style.TextAlign.Center
        )
    } else {
        Row(
            modifier = Modifier.fillMaxWidth(),
            horizontalArrangement = if (isOwn) Arrangement.End else Arrangement.Start
        ) {
            Column(
                horizontalAlignment = if (isOwn) Alignment.End else Alignment.Start,
                modifier = Modifier.widthIn(max = 280.dp)
            ) {
                if (!isOwn) {
                    Text("User #${msg.senderId}", style = MaterialTheme.typography.labelSmall, color = MaterialTheme.colorScheme.onSurfaceVariant)
                }
                Surface(
                    shape = RoundedCornerShape(16.dp),
                    color = if (isOwn) MaterialTheme.colorScheme.primary else MaterialTheme.colorScheme.surfaceVariant,
                    tonalElevation = if (isOwn) 0.dp else 1.dp
                ) {
                    Text(
                        msg.content ?: "",
                        modifier = Modifier.padding(horizontal = 14.dp, vertical = 8.dp),
                        color = if (isOwn) MaterialTheme.colorScheme.onPrimary else MaterialTheme.colorScheme.onSurface,
                        style = MaterialTheme.typography.bodyMedium
                    )
                }
                Row(horizontalArrangement = Arrangement.spacedBy(4.dp)) {
                    Text(formatTime(msg.createdAt), style = MaterialTheme.typography.labelSmall, color = MaterialTheme.colorScheme.onSurfaceVariant)
                    if (msg.isEdited) Text("(edited)", style = MaterialTheme.typography.labelSmall, color = MaterialTheme.colorScheme.onSurfaceVariant)
                    if (msg.isClinical) Text("🏥", fontSize = 10.sp)
                    if (msg.isPriority) Text("⚡", fontSize = 10.sp)
                }
            }
        }
    }
}

// ── Feed View ──

@OptIn(ExperimentalMaterial3Api::class)
@Composable
private fun FeedView(
    posts: List<CommunityPost>,
    feedTopic: String?,
    isLoading: Boolean,
    onTopicChange: (String?) -> Unit,
    onSelectPost: (CommunityPost) -> Unit,
    onLike: (CommunityPost) -> Unit,
    onCreateNew: () -> Unit
) {
    val topics = listOf(null to "All", "general" to "#general", "fitness" to "#fitness", "nutrition" to "#nutrition",
        "mental-health" to "#mental-health", "medications" to "#medications", "lifestyle" to "#lifestyle")

    Column(modifier = Modifier.fillMaxSize()) {
        // Topic filter
        LazyRow(
            modifier = Modifier.padding(horizontal = 16.dp, vertical = 8.dp),
            horizontalArrangement = Arrangement.spacedBy(8.dp)
        ) {
            items(topics) { (value, label) ->
                FilterChip(
                    selected = feedTopic == value,
                    onClick = { onTopicChange(value) },
                    label = { Text(label) }
                )
            }
        }

        if (isLoading) {
            Box(modifier = Modifier.fillMaxSize(), contentAlignment = Alignment.Center) {
                CircularProgressIndicator()
            }
        } else if (posts.isEmpty()) {
            Box(modifier = Modifier.fillMaxSize(), contentAlignment = Alignment.Center) {
                Column(horizontalAlignment = Alignment.CenterHorizontally) {
                    Icon(Icons.Default.Public, null, modifier = Modifier.size(48.dp), tint = MaterialTheme.colorScheme.onSurfaceVariant)
                    Spacer(Modifier.height(8.dp))
                    Text("No posts yet", color = MaterialTheme.colorScheme.onSurfaceVariant)
                    Spacer(Modifier.height(12.dp))
                    Button(onClick = onCreateNew) { Text("Create Post") }
                }
            }
        } else {
            LazyColumn(
                modifier = Modifier.fillMaxSize(),
                contentPadding = PaddingValues(horizontal = 16.dp),
                verticalArrangement = Arrangement.spacedBy(8.dp)
            ) {
                items(posts) { post ->
                    PostCard(post = post, onClick = { onSelectPost(post) }, onLike = { onLike(post) })
                }
            }
        }
    }
}

@Composable
private fun PostCard(post: CommunityPost, onClick: () -> Unit, onLike: () -> Unit) {
    Card(
        modifier = Modifier
            .fillMaxWidth()
            .clickable(onClick = onClick),
        elevation = CardDefaults.cardElevation(defaultElevation = 1.dp)
    ) {
        Column(modifier = Modifier.padding(14.dp)) {
            // Author header
            Row(verticalAlignment = Alignment.CenterVertically) {
                Box(
                    modifier = Modifier
                        .size(32.dp)
                        .clip(CircleShape)
                        .background(MaterialTheme.colorScheme.primary.copy(alpha = 0.12f)),
                    contentAlignment = Alignment.Center
                ) {
                    Text(
                        if (post.isAnonymous) "?" else "#${post.authorId}",
                        style = MaterialTheme.typography.labelSmall,
                        fontWeight = FontWeight.Bold,
                        color = MaterialTheme.colorScheme.primary,
                        fontSize = 9.sp
                    )
                }
                Spacer(Modifier.width(8.dp))
                Column(modifier = Modifier.weight(1f)) {
                    Text(
                        if (post.isAnonymous) "Anonymous" else "User #${post.authorId}",
                        style = MaterialTheme.typography.labelMedium,
                        fontWeight = FontWeight.SemiBold
                    )
                    Text(formatShortDate(post.createdAt), style = MaterialTheme.typography.labelSmall, color = MaterialTheme.colorScheme.onSurfaceVariant)
                }
                if (post.isPinned) {
                    Icon(Icons.Default.PushPin, null, modifier = Modifier.size(14.dp), tint = Color(0xFFFF9800))
                }
                post.topic?.let {
                    Spacer(Modifier.width(4.dp))
                    Text("#$it", style = MaterialTheme.typography.labelSmall, color = MaterialTheme.colorScheme.primary)
                }
            }

            Spacer(Modifier.height(8.dp))

            // Content
            Text(
                post.content.take(300) + if (post.content.length > 300) "…" else "",
                style = MaterialTheme.typography.bodyMedium,
                maxLines = 5,
                overflow = TextOverflow.Ellipsis
            )

            // Health badge
            post.healthCategory?.let { cat ->
                Spacer(Modifier.height(6.dp))
                AssistChip(
                    onClick = {},
                    label = { Text(cat.replace("_", " "), fontSize = 10.sp) },
                    colors = AssistChipDefaults.assistChipColors(
                        containerColor = Color(0xFF4CAF50).copy(alpha = 0.1f),
                        labelColor = Color(0xFF4CAF50)
                    ),
                    modifier = Modifier.height(24.dp)
                )
            }

            Spacer(Modifier.height(8.dp))

            // Engagement row
            Row(
                horizontalArrangement = Arrangement.spacedBy(16.dp),
                verticalAlignment = Alignment.CenterVertically
            ) {
                IconButton(onClick = onLike, modifier = Modifier.size(32.dp)) {
                    Row(verticalAlignment = Alignment.CenterVertically) {
                        Icon(
                            if (post.userLiked == true) Icons.Default.Favorite else Icons.Default.FavoriteBorder,
                            null,
                            modifier = Modifier.size(16.dp),
                            tint = if (post.userLiked == true) Color.Red else MaterialTheme.colorScheme.onSurfaceVariant
                        )
                        Spacer(Modifier.width(2.dp))
                        Text("${post.likeCount}", style = MaterialTheme.typography.labelSmall)
                    }
                }
                Row(verticalAlignment = Alignment.CenterVertically) {
                    Icon(Icons.Default.ChatBubbleOutline, null, modifier = Modifier.size(16.dp), tint = MaterialTheme.colorScheme.onSurfaceVariant)
                    Spacer(Modifier.width(2.dp))
                    Text("${post.replyCount}", style = MaterialTheme.typography.labelSmall)
                }
                Row(verticalAlignment = Alignment.CenterVertically) {
                    Icon(Icons.Default.Visibility, null, modifier = Modifier.size(16.dp), tint = MaterialTheme.colorScheme.onSurfaceVariant)
                    Spacer(Modifier.width(2.dp))
                    Text("${post.viewCount}", style = MaterialTheme.typography.labelSmall)
                }
            }
        }
    }
}

// ── Post Detail View ──

@Composable
private fun PostDetailView(
    post: CommunityPost,
    replies: List<PostReply>,
    onSendReply: (String) -> Unit,
    onLike: () -> Unit
) {
    var replyText by remember { mutableStateOf("") }

    Column(modifier = Modifier.fillMaxSize()) {
        LazyColumn(
            modifier = Modifier.weight(1f),
            contentPadding = PaddingValues(16.dp),
            verticalArrangement = Arrangement.spacedBy(12.dp)
        ) {
            // Post header
            item {
                Row(verticalAlignment = Alignment.CenterVertically) {
                    Box(
                        modifier = Modifier
                            .size(36.dp)
                            .clip(CircleShape)
                            .background(MaterialTheme.colorScheme.primary.copy(alpha = 0.12f)),
                        contentAlignment = Alignment.Center
                    ) {
                        Text(
                            if (post.isAnonymous) "?" else "#${post.authorId}",
                            style = MaterialTheme.typography.labelSmall,
                            fontWeight = FontWeight.Bold,
                            color = MaterialTheme.colorScheme.primary
                        )
                    }
                    Spacer(Modifier.width(8.dp))
                    Column {
                        Text(
                            if (post.isAnonymous) "Anonymous" else "User #${post.authorId}",
                            style = MaterialTheme.typography.titleSmall,
                            fontWeight = FontWeight.SemiBold
                        )
                        Row(horizontalArrangement = Arrangement.spacedBy(6.dp)) {
                            Text(formatShortDate(post.createdAt), style = MaterialTheme.typography.labelSmall, color = MaterialTheme.colorScheme.onSurfaceVariant)
                            post.topic?.let {
                                Text("#$it", style = MaterialTheme.typography.labelSmall, color = MaterialTheme.colorScheme.primary)
                            }
                            if (post.isEdited) Text("(edited)", style = MaterialTheme.typography.labelSmall, color = MaterialTheme.colorScheme.onSurfaceVariant)
                        }
                    }
                }
            }

            // Content
            item {
                Text(post.content, style = MaterialTheme.typography.bodyLarge)
            }

            // Health badge & hashtags
            post.healthCategory?.let { cat ->
                item {
                    AssistChip(
                        onClick = {},
                        label = { Text(cat.replace("_", " "), fontSize = 11.sp) },
                        colors = AssistChipDefaults.assistChipColors(
                            containerColor = Color(0xFF4CAF50).copy(alpha = 0.1f),
                            labelColor = Color(0xFF4CAF50)
                        )
                    )
                }
            }
            post.hashtags?.let { tags ->
                item {
                    Text(
                        tags.split(",").joinToString(" ") { "#${it.trim()}" },
                        style = MaterialTheme.typography.bodySmall,
                        color = MaterialTheme.colorScheme.primary
                    )
                }
            }

            // Engagement
            item {
                HorizontalDivider()
                Row(
                    modifier = Modifier.padding(vertical = 8.dp),
                    horizontalArrangement = Arrangement.spacedBy(20.dp),
                    verticalAlignment = Alignment.CenterVertically
                ) {
                    TextButton(onClick = onLike) {
                        Icon(
                            if (post.userLiked == true) Icons.Default.Favorite else Icons.Default.FavoriteBorder,
                            null,
                            modifier = Modifier.size(18.dp),
                            tint = if (post.userLiked == true) Color.Red else MaterialTheme.colorScheme.onSurfaceVariant
                        )
                        Spacer(Modifier.width(4.dp))
                        Text("${post.likeCount}")
                    }
                    Row(verticalAlignment = Alignment.CenterVertically) {
                        Icon(Icons.Default.ChatBubbleOutline, null, modifier = Modifier.size(18.dp), tint = MaterialTheme.colorScheme.onSurfaceVariant)
                        Spacer(Modifier.width(4.dp))
                        Text("${post.replyCount}", style = MaterialTheme.typography.bodyMedium)
                    }
                    Row(verticalAlignment = Alignment.CenterVertically) {
                        Icon(Icons.Default.Visibility, null, modifier = Modifier.size(18.dp), tint = MaterialTheme.colorScheme.onSurfaceVariant)
                        Spacer(Modifier.width(4.dp))
                        Text("${post.viewCount}", style = MaterialTheme.typography.bodyMedium)
                    }
                }
                HorizontalDivider()
            }

            // Replies header
            item {
                Text("Replies (${replies.size})", style = MaterialTheme.typography.titleSmall, fontWeight = FontWeight.SemiBold)
            }

            if (replies.isEmpty()) {
                item {
                    Text("No replies yet. Be the first!", style = MaterialTheme.typography.bodySmall, color = MaterialTheme.colorScheme.onSurfaceVariant)
                }
            }

            items(replies) { reply ->
                Card(
                    modifier = Modifier.fillMaxWidth(),
                    colors = CardDefaults.cardColors(containerColor = MaterialTheme.colorScheme.surfaceVariant)
                ) {
                    Column(modifier = Modifier.padding(10.dp)) {
                        Row(verticalAlignment = Alignment.CenterVertically) {
                            Box(
                                modifier = Modifier
                                    .size(24.dp)
                                    .clip(CircleShape)
                                    .background(Color(0xFF9C27B0).copy(alpha = 0.12f)),
                                contentAlignment = Alignment.Center
                            ) {
                                Text("#${reply.authorId}", fontSize = 8.sp, fontWeight = FontWeight.Bold, color = Color(0xFF9C27B0))
                            }
                            Spacer(Modifier.width(6.dp))
                            Text("User #${reply.authorId}", style = MaterialTheme.typography.labelSmall, fontWeight = FontWeight.SemiBold)
                            Spacer(Modifier.width(6.dp))
                            Text(formatShortDate(reply.createdAt), style = MaterialTheme.typography.labelSmall, color = MaterialTheme.colorScheme.onSurfaceVariant)
                            if (reply.isEdited) {
                                Spacer(Modifier.width(4.dp))
                                Text("(edited)", style = MaterialTheme.typography.labelSmall, color = MaterialTheme.colorScheme.onSurfaceVariant)
                            }
                        }
                        Spacer(Modifier.height(4.dp))
                        Text(reply.content, style = MaterialTheme.typography.bodySmall)
                    }
                }
            }
        }

        // Reply input
        HorizontalDivider()
        Row(
            modifier = Modifier
                .fillMaxWidth()
                .padding(12.dp),
            verticalAlignment = Alignment.CenterVertically
        ) {
            OutlinedTextField(
                value = replyText,
                onValueChange = { replyText = it },
                modifier = Modifier.weight(1f),
                placeholder = { Text("Write a reply...") },
                singleLine = true,
                shape = RoundedCornerShape(24.dp)
            )
            Spacer(Modifier.width(8.dp))
            IconButton(
                onClick = {
                    if (replyText.isNotBlank()) {
                        onSendReply(replyText)
                        replyText = ""
                    }
                },
                enabled = replyText.isNotBlank()
            ) {
                Icon(
                    Icons.Default.Send,
                    "Reply",
                    tint = if (replyText.isNotBlank()) MaterialTheme.colorScheme.primary else MaterialTheme.colorScheme.onSurfaceVariant
                )
            }
        }
    }
}

// ── Create Conversation Sheet ──

/**
 * Search field + chips that replaced "Member IDs (comma-separated)".
 *
 * A member id is an internal handle — nobody knows their nephrologist's primary
 * key. The lookup only matches a partial name among shared contacts; anyone
 * else needs their full email or phone, so an empty result is a normal outcome
 * and the empty copy says how to reach someone who is not a contact yet.
 */
@OptIn(ExperimentalMaterial3Api::class)
@Composable
private fun RecipientPicker(
    selected: List<RecipientMatch>,
    onChange: (List<RecipientMatch>) -> Unit,
    max: Int?
) {
    var term by remember { mutableStateOf("") }
    var results by remember { mutableStateOf<List<RecipientMatch>>(emptyList()) }
    var searching by remember { mutableStateOf(false) }
    var searchError by remember { mutableStateOf<String?>(null) }
    var searched by remember { mutableStateOf(false) }
    val isFull = max != null && selected.size >= max

    // Debounced: one request per pause in typing, not one per keystroke.
    LaunchedEffect(term) {
        val q = term.trim()
        searched = false
        if (q.length < 2) {
            results = emptyList(); searchError = null
            return@LaunchedEffect
        }
        delay(300)
        searching = true
        try {
            results = ApiClient.getApiService().findRecipients(q)
            searchError = null
        } catch (_: Exception) {
            // An error is not an empty state: "nobody found" would send the
            // user hunting for a contact who is in fact right there.
            results = emptyList()
            searchError = "Could not search right now."
        } finally {
            searching = false
            searched = true
        }
    }

    Text(
        if (max == 1) "Recipient" else "Recipients",
        style = MaterialTheme.typography.labelLarge
    )
    Spacer(Modifier.height(6.dp))

    selected.forEach { person ->
        Row(
            verticalAlignment = Alignment.CenterVertically,
            modifier = Modifier.fillMaxWidth().padding(vertical = 4.dp)
        ) {
            Column(Modifier.weight(1f)) {
                Text(person.fullName, fontWeight = FontWeight.SemiBold)
                if (person.subtitle.isNotBlank()) {
                    Text(
                        person.subtitle,
                        style = MaterialTheme.typography.bodySmall,
                        color = MaterialTheme.colorScheme.onSurfaceVariant
                    )
                }
            }
            IconButton(onClick = { onChange(selected.filterNot { it.id == person.id }) }) {
                Icon(Icons.Default.Close, contentDescription = "Remove ${person.fullName}")
            }
        }
    }

    if (!isFull) {
        OutlinedTextField(
            value = term,
            onValueChange = { term = it },
            label = { Text("Search by name, email or phone") },
            singleLine = true,
            trailingIcon = {
                if (searching) {
                    CircularProgressIndicator(Modifier.size(18.dp), strokeWidth = 2.dp)
                }
            },
            modifier = Modifier.fillMaxWidth()
        )

        results.forEach { person ->
            Row(
                modifier = Modifier
                    .fillMaxWidth()
                    .clickable {
                        if (selected.none { it.id == person.id }) {
                            onChange(selected + person)
                            term = ""; results = emptyList(); searched = false
                        }
                    }
                    .padding(vertical = 8.dp)
            ) {
                Column {
                    Text(person.fullName, fontWeight = FontWeight.SemiBold)
                    if (person.subtitle.isNotBlank()) {
                        Text(
                            person.subtitle,
                            style = MaterialTheme.typography.bodySmall,
                            color = MaterialTheme.colorScheme.onSurfaceVariant
                        )
                    }
                }
            }
        }

        val error = searchError
        if (error != null) {
            Text(error, style = MaterialTheme.typography.bodySmall, color = MaterialTheme.colorScheme.error)
        } else if (searched && term.trim().length >= 2 && results.isEmpty()) {
            Text(
                "Nobody found. You can find your own contacts by name — to reach " +
                    "anyone else, enter their full email address or phone number.",
                style = MaterialTheme.typography.bodySmall,
                color = MaterialTheme.colorScheme.onSurfaceVariant
            )
        }
    } else {
        Text(
            "A direct message goes to one person. Remove them to pick someone else.",
            style = MaterialTheme.typography.bodySmall,
            color = MaterialTheme.colorScheme.onSurfaceVariant
        )
    }
}

@OptIn(ExperimentalMaterial3Api::class)
@Composable
private fun CreateConversationSheet(
    defaultType: String,
    typeLocked: Boolean,
    errorMessage: String?,
    onDismiss: () -> Unit,
    onCreate: (CreateConversationRequest) -> Unit
) {
    var convType by remember { mutableStateOf(defaultType) }
    var title by remember { mutableStateOf("") }
    var description by remember { mutableStateOf("") }
    var recipients by remember { mutableStateOf<List<RecipientMatch>>(emptyList()) }
    var specialty by remember { mutableStateOf("") }
    var priority by remember { mutableStateOf("routine") }
    var isUrgent by remember { mutableStateOf(false) }
    var typeExpanded by remember { mutableStateOf(false) }
    var priorityExpanded by remember { mutableStateOf(false) }
    var submitting by remember { mutableStateOf(false) }
    // The filter chips already chose the type; do not ask a second time.
    var editingType by remember { mutableStateOf(!typeLocked) }

    val convTypes = listOf("direct" to "Direct Message", "clinical" to "Clinical", "group" to "Group Chat", "care_team" to "Care Team")
    val priorities = listOf("routine", "urgent", "stat")
    val isDirect = convType == "direct"

    // A rejected create must release the button, or the sheet locks up.
    LaunchedEffect(errorMessage) { if (errorMessage != null) submitting = false }

    ModalBottomSheet(onDismissRequest = onDismiss) {
        Column(
            modifier = Modifier
                .padding(horizontal = 24.dp, vertical = 16.dp)
                .fillMaxWidth()
                .verticalScroll(rememberScrollState())
        ) {
            Text("New Conversation", style = MaterialTheme.typography.headlineSmall, fontWeight = FontWeight.Bold)
            Spacer(Modifier.height(16.dp))

            if (editingType) {
                ExposedDropdownMenuBox(expanded = typeExpanded, onExpandedChange = { typeExpanded = it }) {
                    OutlinedTextField(
                        value = convTypes.find { it.first == convType }?.second ?: "",
                        onValueChange = {},
                        readOnly = true,
                        label = { Text("Type") },
                        trailingIcon = { ExposedDropdownMenuDefaults.TrailingIcon(expanded = typeExpanded) },
                        modifier = Modifier
                            .fillMaxWidth()
                            .menuAnchor()
                    )
                    ExposedDropdownMenu(expanded = typeExpanded, onDismissRequest = { typeExpanded = false }) {
                        convTypes.forEach { (value, label) ->
                            DropdownMenuItem(text = { Text(label) }, onClick = { convType = value; typeExpanded = false })
                        }
                    }
                }
            } else {
                Row(verticalAlignment = Alignment.CenterVertically) {
                    Text(
                        convTypes.find { it.first == convType }?.second ?: convType,
                        color = MaterialTheme.colorScheme.onSurfaceVariant
                    )
                    Spacer(Modifier.width(12.dp))
                    TextButton(onClick = { editingType = true }) { Text("Change") }
                }
            }
            Spacer(Modifier.height(12.dp))

            RecipientPicker(
                selected = recipients,
                onChange = { recipients = it },
                max = if (isDirect) 1 else null
            )
            Spacer(Modifier.height(12.dp))

            // A direct message is named by whoever is in it.
            if (!isDirect) {
                OutlinedTextField(
                    value = title,
                    onValueChange = { title = it },
                    label = { Text("Name") },
                    modifier = Modifier.fillMaxWidth()
                )
                Spacer(Modifier.height(12.dp))
            }

            OutlinedTextField(
                value = description,
                onValueChange = { description = it },
                label = { Text("Description (optional)") },
                modifier = Modifier.fillMaxWidth()
            )

            if (convType == "clinical" || convType == "care_team") {
                Spacer(Modifier.height(12.dp))
                OutlinedTextField(
                    value = specialty,
                    onValueChange = { specialty = it },
                    label = { Text("Specialty") },
                    modifier = Modifier.fillMaxWidth()
                )
                Spacer(Modifier.height(12.dp))
                ExposedDropdownMenuBox(expanded = priorityExpanded, onExpandedChange = { priorityExpanded = it }) {
                    OutlinedTextField(
                        value = priority.replaceFirstChar { it.uppercase() },
                        onValueChange = {},
                        readOnly = true,
                        label = { Text("Priority") },
                        trailingIcon = { ExposedDropdownMenuDefaults.TrailingIcon(expanded = priorityExpanded) },
                        modifier = Modifier
                            .fillMaxWidth()
                            .menuAnchor()
                    )
                    ExposedDropdownMenu(expanded = priorityExpanded, onDismissRequest = { priorityExpanded = false }) {
                        priorities.forEach { p ->
                            DropdownMenuItem(text = { Text(p.replaceFirstChar { it.uppercase() }) }, onClick = { priority = p; priorityExpanded = false })
                        }
                    }
                }
                Spacer(Modifier.height(8.dp))
                Row(verticalAlignment = Alignment.CenterVertically) {
                    Text("Mark as Urgent")
                    Spacer(Modifier.weight(1f))
                    Switch(checked = isUrgent, onCheckedChange = { isUrgent = it })
                }
            }

            if (errorMessage != null) {
                Spacer(Modifier.height(12.dp))
                Text(errorMessage, style = MaterialTheme.typography.bodySmall, color = MaterialTheme.colorScheme.error)
            }

            Spacer(Modifier.height(20.dp))
            Button(
                onClick = {
                    submitting = true
                    onCreate(CreateConversationRequest(
                        conversationType = convType,
                        title = title.ifBlank { null },
                        description = description.ifBlank { null },
                        memberIds = recipients.map { it.id },
                        specialty = specialty.ifBlank { null },
                        priority = priority,
                        isUrgent = isUrgent
                    ))
                },
                modifier = Modifier.fillMaxWidth(),
                enabled = !submitting && recipients.isNotEmpty()
            ) {
                Text(if (submitting) "Creating..." else "Create Conversation")
            }
            Spacer(Modifier.height(24.dp))
        }
    }
}

// ── Create Post Sheet ──

@OptIn(ExperimentalMaterial3Api::class)
@Composable
private fun CreatePostSheet(
    onDismiss: () -> Unit,
    onCreate: (CreatePostRequest) -> Unit
) {
    var content by remember { mutableStateOf("") }
    var visibility by remember { mutableStateOf("public") }
    var topic by remember { mutableStateOf("") }
    var healthCategory by remember { mutableStateOf("") }
    var hashtags by remember { mutableStateOf("") }
    var isAnonymous by remember { mutableStateOf(false) }
    var visExpanded by remember { mutableStateOf(false) }
    var topicExpanded by remember { mutableStateOf(false) }
    var catExpanded by remember { mutableStateOf(false) }
    var submitting by remember { mutableStateOf(false) }

    val visibilities = listOf("public" to "🌍 Public", "followers" to "👥 Followers", "connections" to "🤝 Connections", "private" to "🔒 Private")
    val topics = listOf("" to "— None —", "general" to "General", "fitness" to "Fitness", "nutrition" to "Nutrition",
        "mental-health" to "Mental Health", "medications" to "Medications", "lifestyle" to "Lifestyle", "community" to "Community")
    val categories = listOf("" to "— None —", "fitness" to "Fitness", "nutrition" to "Nutrition", "mood" to "Mood",
        "mental_health" to "Mental Health", "medications" to "Medications", "labs" to "Labs", "lifestyle" to "Lifestyle", "general" to "General")

    ModalBottomSheet(onDismissRequest = onDismiss) {
        Column(
            modifier = Modifier
                .padding(horizontal = 24.dp, vertical = 16.dp)
                .fillMaxWidth()
        ) {
            Text("Create Post", style = MaterialTheme.typography.headlineSmall, fontWeight = FontWeight.Bold)
            Spacer(Modifier.height(16.dp))

            OutlinedTextField(
                value = content,
                onValueChange = { if (it.length <= 5000) content = it },
                label = { Text("What's on your mind?") },
                modifier = Modifier
                    .fillMaxWidth()
                    .heightIn(min = 100.dp),
                maxLines = 8
            )
            Text("${content.length}/5000", style = MaterialTheme.typography.labelSmall, color = MaterialTheme.colorScheme.onSurfaceVariant)
            Spacer(Modifier.height(12.dp))

            // Visibility
            ExposedDropdownMenuBox(expanded = visExpanded, onExpandedChange = { visExpanded = it }) {
                OutlinedTextField(
                    value = visibilities.find { it.first == visibility }?.second ?: "",
                    onValueChange = {},
                    readOnly = true,
                    label = { Text("Visibility") },
                    trailingIcon = { ExposedDropdownMenuDefaults.TrailingIcon(expanded = visExpanded) },
                    modifier = Modifier
                        .fillMaxWidth()
                        .menuAnchor()
                )
                ExposedDropdownMenu(expanded = visExpanded, onDismissRequest = { visExpanded = false }) {
                    visibilities.forEach { (v, l) ->
                        DropdownMenuItem(text = { Text(l) }, onClick = { visibility = v; visExpanded = false })
                    }
                }
            }
            Spacer(Modifier.height(12.dp))

            // Topic
            ExposedDropdownMenuBox(expanded = topicExpanded, onExpandedChange = { topicExpanded = it }) {
                OutlinedTextField(
                    value = topics.find { it.first == topic }?.second ?: "— None —",
                    onValueChange = {},
                    readOnly = true,
                    label = { Text("Topic") },
                    trailingIcon = { ExposedDropdownMenuDefaults.TrailingIcon(expanded = topicExpanded) },
                    modifier = Modifier
                        .fillMaxWidth()
                        .menuAnchor()
                )
                ExposedDropdownMenu(expanded = topicExpanded, onDismissRequest = { topicExpanded = false }) {
                    topics.forEach { (v, l) ->
                        DropdownMenuItem(text = { Text(l) }, onClick = { topic = v; topicExpanded = false })
                    }
                }
            }
            Spacer(Modifier.height(12.dp))

            // Health Category
            ExposedDropdownMenuBox(expanded = catExpanded, onExpandedChange = { catExpanded = it }) {
                OutlinedTextField(
                    value = categories.find { it.first == healthCategory }?.second ?: "— None —",
                    onValueChange = {},
                    readOnly = true,
                    label = { Text("Health Category") },
                    trailingIcon = { ExposedDropdownMenuDefaults.TrailingIcon(expanded = catExpanded) },
                    modifier = Modifier
                        .fillMaxWidth()
                        .menuAnchor()
                )
                ExposedDropdownMenu(expanded = catExpanded, onDismissRequest = { catExpanded = false }) {
                    categories.forEach { (v, l) ->
                        DropdownMenuItem(text = { Text(l) }, onClick = { healthCategory = v; catExpanded = false })
                    }
                }
            }
            Spacer(Modifier.height(12.dp))

            OutlinedTextField(
                value = hashtags,
                onValueChange = { hashtags = it },
                label = { Text("Hashtags (comma-separated)") },
                modifier = Modifier.fillMaxWidth()
            )
            Spacer(Modifier.height(8.dp))
            Row(verticalAlignment = Alignment.CenterVertically) {
                Text("Post Anonymously")
                Spacer(Modifier.weight(1f))
                Switch(checked = isAnonymous, onCheckedChange = { isAnonymous = it })
            }

            Spacer(Modifier.height(20.dp))
            Button(
                onClick = {
                    submitting = true
                    onCreate(CreatePostRequest(
                        content = content,
                        visibility = visibility,
                        topic = topic.ifBlank { null },
                        healthCategory = healthCategory.ifBlank { null },
                        hashtags = hashtags.ifBlank { null },
                        isAnonymous = isAnonymous
                    ))
                },
                modifier = Modifier.fillMaxWidth(),
                enabled = !submitting && content.isNotBlank()
            ) {
                Text(if (submitting) "Publishing..." else "Publish")
            }
            Spacer(Modifier.height(24.dp))
        }
    }
}

// ── Date Helpers ──

// Display in the device's LOCAL timezone (server timestamps are UTC).
private fun formatShortDate(iso: String): String = com.alafia.android.util.AppDate.shortDateTime(iso)

private fun formatTime(iso: String): String = com.alafia.android.util.AppDate.time(iso)
