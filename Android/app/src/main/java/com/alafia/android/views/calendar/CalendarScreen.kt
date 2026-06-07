package com.alafia.android.views.calendar
import com.alafia.android.util.ErrorUtil

import android.widget.Toast
import androidx.compose.foundation.background
import androidx.compose.foundation.clickable
import androidx.compose.foundation.horizontalScroll
import androidx.compose.foundation.layout.*
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.lazy.items
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.shape.CircleShape
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.foundation.verticalScroll
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
import androidx.compose.ui.text.style.TextDecoration
import androidx.compose.ui.text.style.TextOverflow
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import com.alafia.android.api.ApiClient
import com.alafia.android.models.CalendarEvent
import com.alafia.android.schemas.CalendarEventRequest
import com.alafia.android.schemas.CalendarEventUpdateRequest
import kotlinx.coroutines.launch
import java.time.LocalDate
import java.time.YearMonth
import java.time.format.DateTimeFormatter
import java.time.format.TextStyle
import java.util.Locale
import androidx.navigation.NavHostController

// Category colors & labels
data class CategoryMeta(val label: String, val color: Color)

val categoryMap = mapOf(
    "appointment" to CategoryMeta("Appointment", Color(0xFF4CAF50)),
    "meal" to CategoryMeta("Meal", Color(0xFFFF9800)),
    "medication" to CategoryMeta("Medication", Color(0xFF2196F3)),
    "exercise" to CategoryMeta("Exercise", Color(0xFFF44336)),
    "meditation" to CategoryMeta("Meditation", Color(0xFF9C27B0)),
    "therapy" to CategoryMeta("Therapy", Color(0xFF00BCD4)),
    "lab" to CategoryMeta("Lab", Color(0xFF795548)),
    "wellness" to CategoryMeta("Wellness", Color(0xFFE91E63)),
    "custom" to CategoryMeta("Custom", Color(0xFF9E9E9E))
)

val priorityColors = mapOf(
    "high" to Color(0xFFF44336),
    "medium" to Color(0xFFFF9800),
    "low" to Color(0xFF9E9E9E)
)

val categoryKeys = listOf("appointment", "meal", "medication", "exercise", "meditation", "therapy", "lab", "wellness", "custom")
val recurrenceOptions = listOf("none", "daily", "weekly", "biweekly", "monthly", "yearly")
val priorityOptions = listOf("", "low", "medium", "high")

@OptIn(ExperimentalMaterial3Api::class)
@Composable
fun CalendarScreen(navController: NavHostController) {
    var events by remember { mutableStateOf<List<CalendarEvent>>(emptyList()) }
    var viewMonth by remember { mutableStateOf(YearMonth.now()) }
    var selectedDate by remember { mutableStateOf(LocalDate.now()) }
    var filterCategory by remember { mutableStateOf("") }
    var isLoading by remember { mutableStateOf(true) }
    var showForm by remember { mutableStateOf(false) }
    var editEvent by remember { mutableStateOf<CalendarEvent?>(null) }
    val context = LocalContext.current
    val scope = rememberCoroutineScope()
    val fmt = DateTimeFormatter.ofPattern("yyyy-MM-dd")

    val selectedDateStr = selectedDate.format(fmt)
    val eventsOnDate = events.filter { it.eventDate == selectedDateStr }
        .let { list -> if (filterCategory.isNotEmpty()) list.filter { it.category == filterCategory } else list }

    val eventCountByDate = events.groupBy { it.eventDate }.mapValues { it.value.size }

    fun loadMonth() {
        scope.launch {
            isLoading = true
            try {
                val start = viewMonth.atDay(1).format(fmt)
                val end = viewMonth.atEndOfMonth().format(fmt)
                events = ApiClient.getApiService().getCalendarEvents(startDate = start, endDate = end)
            } catch (e: Exception) {
                Toast.makeText(context, ErrorUtil.userMessage(e), Toast.LENGTH_SHORT).show()
            }
            isLoading = false
        }
    }

    LaunchedEffect(viewMonth) { loadMonth() }

    Scaffold(
        topBar = {
            TopAppBar(
                title = { Text("Calendar") },
                navigationIcon = {
                    IconButton(onClick = { navController.popBackStack() }) {
                        Icon(Icons.Default.ArrowBack, contentDescription = "Back")
                    }
                },
                actions = {
                    IconButton(onClick = { editEvent = null; showForm = true }) {
                        Icon(Icons.Default.Add, contentDescription = "Add Event")
                    }
                }
            )
        }
    ) { padding ->
    Column(modifier = Modifier.fillMaxSize().padding(padding)) {
        // Month navigator
        Row(
            modifier = Modifier.fillMaxWidth().padding(horizontal = 16.dp),
            horizontalArrangement = Arrangement.SpaceBetween,
            verticalAlignment = Alignment.CenterVertically
        ) {
            IconButton(onClick = { viewMonth = viewMonth.minusMonths(1) }) {
                Icon(Icons.Default.ChevronLeft, contentDescription = "Previous")
            }
            Text(
                "${viewMonth.month.getDisplayName(TextStyle.FULL, Locale.getDefault())} ${viewMonth.year}",
                style = MaterialTheme.typography.titleLarge,
                fontWeight = FontWeight.SemiBold
            )
            IconButton(onClick = { viewMonth = viewMonth.plusMonths(1) }) {
                Icon(Icons.Default.ChevronRight, contentDescription = "Next")
            }
        }

        // Calendar grid
        CalendarGrid(
            yearMonth = viewMonth,
            selectedDate = selectedDate,
            eventCounts = eventCountByDate,
            onDayClick = { selectedDate = it }
        )

        // Category filters
        Row(
            modifier = Modifier.fillMaxWidth().padding(horizontal = 16.dp, vertical = 8.dp)
                .horizontalScroll(rememberScrollState()),
            horizontalArrangement = Arrangement.spacedBy(6.dp)
        ) {
            FilterChip(
                selected = filterCategory.isEmpty(),
                onClick = { filterCategory = "" },
                label = { Text("All") }
            )
            categoryKeys.forEach { key ->
                val meta = categoryMap[key]!!
                FilterChip(
                    selected = filterCategory == key,
                    onClick = { filterCategory = if (filterCategory == key) "" else key },
                    label = { Text(meta.label) },
                    colors = FilterChipDefaults.filterChipColors(
                        selectedContainerColor = meta.color.copy(alpha = 0.2f),
                        selectedLabelColor = meta.color
                    )
                )
            }
        }

        // Day header
        Row(
            modifier = Modifier.fillMaxWidth().padding(horizontal = 16.dp, vertical = 4.dp),
            horizontalArrangement = Arrangement.SpaceBetween
        ) {
            Text(
                selectedDate.format(DateTimeFormatter.ofPattern("EEEE, MMMM d")),
                style = MaterialTheme.typography.titleMedium,
                fontWeight = FontWeight.SemiBold
            )
            Text(
                "${eventsOnDate.size} event${if (eventsOnDate.size != 1) "s" else ""}",
                style = MaterialTheme.typography.bodySmall,
                color = MaterialTheme.colorScheme.onSurfaceVariant
            )
        }

        // Events list
        if (eventsOnDate.isEmpty()) {
            Box(
                modifier = Modifier.fillMaxWidth().weight(1f),
                contentAlignment = Alignment.Center
            ) {
                Column(horizontalAlignment = Alignment.CenterHorizontally) {
                    Text("📅", fontSize = 48.sp)
                    Spacer(Modifier.height(8.dp))
                    Text("No events on this day", style = MaterialTheme.typography.titleMedium)
                    Spacer(Modifier.height(8.dp))
                    Button(onClick = { editEvent = null; showForm = true }) {
                        Text("Add Event")
                    }
                }
            }
        } else {
            LazyColumn(
                modifier = Modifier.weight(1f),
                contentPadding = PaddingValues(horizontal = 16.dp, vertical = 8.dp),
                verticalArrangement = Arrangement.spacedBy(8.dp)
            ) {
                items(eventsOnDate) { ev ->
                    EventCard(
                        event = ev,
                        onComplete = {
                            scope.launch {
                                try {
                                    ApiClient.getApiService().completeCalendarEvent(ev.id)
                                    loadMonth()
                                } catch (e: Exception) {
                                    Toast.makeText(context, ErrorUtil.userMessage(e), Toast.LENGTH_SHORT).show()
                                }
                            }
                        },
                        onEdit = { editEvent = ev; showForm = true },
                        onDelete = {
                            scope.launch {
                                try {
                                    ApiClient.getApiService().deleteCalendarEvent(ev.id)
                                    loadMonth()
                                } catch (e: Exception) {
                                    Toast.makeText(context, "Delete failed: ${e.message}", Toast.LENGTH_SHORT).show()
                                }
                            }
                        }
                    )
                }
            }
        }
    }

    if (showForm) {
        EventFormDialog(
            editEvent = editEvent,
            defaultDate = selectedDateStr,
            onDismiss = { showForm = false; editEvent = null },
            onSaved = { showForm = false; editEvent = null; loadMonth() }
        )
    }
}
}

@Composable
fun CalendarGrid(
    yearMonth: YearMonth,
    selectedDate: LocalDate,
    eventCounts: Map<String, Int>,
    onDayClick: (LocalDate) -> Unit
) {
    val firstDay = yearMonth.atDay(1)
    val firstDayOfWeek = firstDay.dayOfWeek.value % 7 // Sunday=0
    val daysInMonth = yearMonth.lengthOfMonth()
    val today = LocalDate.now()
    val fmt = DateTimeFormatter.ofPattern("yyyy-MM-dd")
    val weekDays = listOf("S", "M", "T", "W", "T", "F", "S")

    Card(
        modifier = Modifier.fillMaxWidth().padding(horizontal = 16.dp),
        colors = CardDefaults.cardColors(containerColor = MaterialTheme.colorScheme.surfaceVariant)
    ) {
        Column(modifier = Modifier.padding(12.dp)) {
            // Week header
            Row(modifier = Modifier.fillMaxWidth()) {
                weekDays.forEach { d ->
                    Text(
                        d,
                        modifier = Modifier.weight(1f),
                        textAlign = androidx.compose.ui.text.style.TextAlign.Center,
                        style = MaterialTheme.typography.labelSmall,
                        color = MaterialTheme.colorScheme.onSurfaceVariant
                    )
                }
            }
            Spacer(Modifier.height(4.dp))

            var day = 1 - firstDayOfWeek
            while (day <= daysInMonth) {
                Row(modifier = Modifier.fillMaxWidth()) {
                    for (col in 0..6) {
                        if (day in 1..daysInMonth) {
                            val date = yearMonth.atDay(day)
                            val dateStr = date.format(fmt)
                            val isToday = date == today
                            val isSelected = date == selectedDate
                            val hasEvents = (eventCounts[dateStr] ?: 0) > 0

                            Box(
                                modifier = Modifier
                                    .weight(1f)
                                    .aspectRatio(1f)
                                    .clip(CircleShape)
                                    .background(
                                        when {
                                            isSelected -> MaterialTheme.colorScheme.primary
                                            isToday -> MaterialTheme.colorScheme.primary.copy(alpha = 0.15f)
                                            else -> Color.Transparent
                                        }
                                    )
                                    .clickable { onDayClick(date) },
                                contentAlignment = Alignment.Center
                            ) {
                                Column(horizontalAlignment = Alignment.CenterHorizontally) {
                                    Text(
                                        "$day",
                                        color = when {
                                            isSelected -> MaterialTheme.colorScheme.onPrimary
                                            isToday -> MaterialTheme.colorScheme.primary
                                            else -> MaterialTheme.colorScheme.onSurface
                                        },
                                        fontWeight = if (isToday) FontWeight.Bold else FontWeight.Normal,
                                        fontSize = 14.sp
                                    )
                                    Box(
                                        modifier = Modifier
                                            .size(4.dp)
                                            .clip(CircleShape)
                                            .background(if (hasEvents) MaterialTheme.colorScheme.primary else Color.Transparent)
                                    )
                                }
                            }
                        } else {
                            Spacer(Modifier.weight(1f))
                        }
                        day++
                    }
                }
            }
        }
    }
}

@Composable
fun EventCard(
    event: CalendarEvent,
    onComplete: () -> Unit,
    onEdit: () -> Unit,
    onDelete: () -> Unit
) {
    val meta = categoryMap[event.category] ?: CategoryMeta("Other", Color.Gray)

    Card(
        modifier = Modifier.fillMaxWidth(),
        colors = CardDefaults.cardColors(
            containerColor = if (event.status == "cancelled")
                MaterialTheme.colorScheme.surfaceVariant.copy(alpha = 0.5f)
            else MaterialTheme.colorScheme.surface
        )
    ) {
        Row(modifier = Modifier.padding(12.dp)) {
            // Color bar
            Box(
                modifier = Modifier
                    .width(4.dp)
                    .height(80.dp)
                    .clip(RoundedCornerShape(2.dp))
                    .background(meta.color)
            )
            Spacer(Modifier.width(12.dp))

            // Content
            Column(modifier = Modifier.weight(1f)) {
                // Badges row
                Row(horizontalArrangement = Arrangement.spacedBy(4.dp)) {
                    Badge(containerColor = meta.color) { Text(meta.label, fontSize = 10.sp) }
                    event.priority?.let { p ->
                        val pc = priorityColors[p] ?: Color.Gray
                        Badge(containerColor = pc) { Text(p.replaceFirstChar { it.uppercase() }, fontSize = 10.sp) }
                    }
                    if (event.status != "scheduled") {
                        Badge(
                            containerColor = if (event.status == "completed") Color(0xFF4CAF50) else Color(0xFFF44336)
                        ) { Text(event.status.replaceFirstChar { it.uppercase() }, fontSize = 10.sp) }
                    }
                }

                Spacer(Modifier.height(4.dp))

                Text(
                    event.title,
                    style = MaterialTheme.typography.bodyLarge,
                    fontWeight = FontWeight.SemiBold,
                    textDecoration = if (event.status == "completed") TextDecoration.LineThrough else TextDecoration.None
                )

                event.description?.takeIf { it.isNotEmpty() }?.let {
                    Text(it, style = MaterialTheme.typography.bodySmall, color = MaterialTheme.colorScheme.onSurfaceVariant, maxLines = 1, overflow = TextOverflow.Ellipsis)
                }

                Row(horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                    if (event.allDay) {
                        Text("🕐 All day", style = MaterialTheme.typography.labelSmall, color = MaterialTheme.colorScheme.onSurfaceVariant)
                    } else {
                        event.startTime?.let { st ->
                            val display = st.take(5) + (event.endTime?.let { " – ${it.take(5)}" } ?: "")
                            Text("🕐 $display", style = MaterialTheme.typography.labelSmall, color = MaterialTheme.colorScheme.onSurfaceVariant)
                        }
                    }
                    event.location?.takeIf { it.isNotEmpty() }?.let {
                        Text("📍 $it", style = MaterialTheme.typography.labelSmall, color = MaterialTheme.colorScheme.onSurfaceVariant, maxLines = 1, overflow = TextOverflow.Ellipsis)
                    }
                    event.recurrence?.let {
                        Text("🔁 $it", style = MaterialTheme.typography.labelSmall, color = MaterialTheme.colorScheme.onSurfaceVariant)
                    }
                }
            }

            // Actions
            Column(verticalArrangement = Arrangement.spacedBy(4.dp)) {
                if (event.status == "scheduled") {
                    IconButton(onClick = onComplete, modifier = Modifier.size(32.dp)) {
                        Icon(Icons.Default.CheckCircle, contentDescription = "Complete", tint = Color(0xFF4CAF50))
                    }
                }
                IconButton(onClick = onEdit, modifier = Modifier.size(32.dp)) {
                    Icon(Icons.Default.Edit, contentDescription = "Edit", tint = MaterialTheme.colorScheme.primary)
                }
                IconButton(onClick = onDelete, modifier = Modifier.size(32.dp)) {
                    Icon(Icons.Default.Delete, contentDescription = "Delete", tint = MaterialTheme.colorScheme.error)
                }
            }
        }
    }
}

@OptIn(ExperimentalMaterial3Api::class)
@Composable
fun EventFormDialog(
    editEvent: CalendarEvent?,
    defaultDate: String,
    onDismiss: () -> Unit,
    onSaved: () -> Unit
) {
    val context = LocalContext.current
    val scope = rememberCoroutineScope()
    val isEdit = editEvent != null

    var title by remember { mutableStateOf(editEvent?.title ?: "") }
    var desc by remember { mutableStateOf(editEvent?.description ?: "") }
    var category by remember { mutableStateOf(editEvent?.category ?: "appointment") }
    var eventDate by remember { mutableStateOf(editEvent?.eventDate ?: defaultDate) }
    var startTime by remember { mutableStateOf(editEvent?.startTime?.take(5) ?: "") }
    var endTime by remember { mutableStateOf(editEvent?.endTime?.take(5) ?: "") }
    var allDay by remember { mutableStateOf(editEvent?.allDay ?: false) }
    var recurrence by remember { mutableStateOf(editEvent?.recurrence ?: "none") }
    var location by remember { mutableStateOf(editEvent?.location ?: "") }
    var priority by remember { mutableStateOf(editEvent?.priority ?: "") }
    var notes by remember { mutableStateOf(editEvent?.notes ?: "") }
    var reminderMin by remember { mutableStateOf(editEvent?.reminderMinutes?.toString() ?: "") }
    var saving by remember { mutableStateOf(false) }
    var categoryExpanded by remember { mutableStateOf(false) }
    var recurrenceExpanded by remember { mutableStateOf(false) }
    var priorityExpanded by remember { mutableStateOf(false) }

    ModalBottomSheet(onDismissRequest = onDismiss) {
        Column(
            modifier = Modifier
                .fillMaxWidth()
                .padding(horizontal = 16.dp, vertical = 8.dp)
                .verticalScroll(rememberScrollState())
        ) {
            Text(
                if (isEdit) "Edit Event" else "New Event",
                style = MaterialTheme.typography.headlineSmall,
                fontWeight = FontWeight.Bold
            )
            Spacer(Modifier.height(16.dp))

            OutlinedTextField(
                value = title, onValueChange = { title = it },
                label = { Text("Title") },
                modifier = Modifier.fillMaxWidth(),
                singleLine = true
            )
            Spacer(Modifier.height(8.dp))

            // Category dropdown
            ExposedDropdownMenuBox(
                expanded = categoryExpanded,
                onExpandedChange = { categoryExpanded = it }
            ) {
                OutlinedTextField(
                    value = categoryMap[category]?.label ?: category,
                    onValueChange = {},
                    readOnly = true,
                    label = { Text("Category") },
                    trailingIcon = { ExposedDropdownMenuDefaults.TrailingIcon(expanded = categoryExpanded) },
                    modifier = Modifier.fillMaxWidth().menuAnchor()
                )
                ExposedDropdownMenu(expanded = categoryExpanded, onDismissRequest = { categoryExpanded = false }) {
                    categoryKeys.forEach { key ->
                        DropdownMenuItem(
                            text = { Text(categoryMap[key]!!.label) },
                            onClick = { category = key; categoryExpanded = false }
                        )
                    }
                }
            }
            Spacer(Modifier.height(8.dp))

            OutlinedTextField(
                value = desc, onValueChange = { desc = it },
                label = { Text("Description") },
                modifier = Modifier.fillMaxWidth(),
                minLines = 2, maxLines = 4
            )
            Spacer(Modifier.height(8.dp))

            OutlinedTextField(
                value = eventDate, onValueChange = { eventDate = it },
                label = { Text("Date (YYYY-MM-DD)") },
                modifier = Modifier.fillMaxWidth(),
                singleLine = true
            )
            Spacer(Modifier.height(8.dp))

            Row(verticalAlignment = Alignment.CenterVertically) {
                Checkbox(checked = allDay, onCheckedChange = { allDay = it })
                Text("All Day")
            }

            if (!allDay) {
                Row(modifier = Modifier.fillMaxWidth(), horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                    OutlinedTextField(
                        value = startTime, onValueChange = { startTime = it },
                        label = { Text("Start (HH:MM)") },
                        modifier = Modifier.weight(1f),
                        singleLine = true
                    )
                    OutlinedTextField(
                        value = endTime, onValueChange = { endTime = it },
                        label = { Text("End (HH:MM)") },
                        modifier = Modifier.weight(1f),
                        singleLine = true
                    )
                }
                Spacer(Modifier.height(8.dp))
            }

            // Recurrence dropdown
            ExposedDropdownMenuBox(
                expanded = recurrenceExpanded,
                onExpandedChange = { recurrenceExpanded = it }
            ) {
                OutlinedTextField(
                    value = if (recurrence == "none") "No repeat" else recurrence.replaceFirstChar { it.uppercase() },
                    onValueChange = {},
                    readOnly = true,
                    label = { Text("Recurrence") },
                    trailingIcon = { ExposedDropdownMenuDefaults.TrailingIcon(expanded = recurrenceExpanded) },
                    modifier = Modifier.fillMaxWidth().menuAnchor()
                )
                ExposedDropdownMenu(expanded = recurrenceExpanded, onDismissRequest = { recurrenceExpanded = false }) {
                    recurrenceOptions.forEach { opt ->
                        DropdownMenuItem(
                            text = { Text(if (opt == "none") "No repeat" else opt.replaceFirstChar { it.uppercase() }) },
                            onClick = { recurrence = opt; recurrenceExpanded = false }
                        )
                    }
                }
            }
            Spacer(Modifier.height(8.dp))

            OutlinedTextField(
                value = location, onValueChange = { location = it },
                label = { Text("Location") },
                modifier = Modifier.fillMaxWidth(),
                singleLine = true
            )
            Spacer(Modifier.height(8.dp))

            // Priority dropdown
            ExposedDropdownMenuBox(
                expanded = priorityExpanded,
                onExpandedChange = { priorityExpanded = it }
            ) {
                OutlinedTextField(
                    value = if (priority.isEmpty()) "None" else priority.replaceFirstChar { it.uppercase() },
                    onValueChange = {},
                    readOnly = true,
                    label = { Text("Priority") },
                    trailingIcon = { ExposedDropdownMenuDefaults.TrailingIcon(expanded = priorityExpanded) },
                    modifier = Modifier.fillMaxWidth().menuAnchor()
                )
                ExposedDropdownMenu(expanded = priorityExpanded, onDismissRequest = { priorityExpanded = false }) {
                    priorityOptions.forEach { opt ->
                        DropdownMenuItem(
                            text = { Text(if (opt.isEmpty()) "None" else opt.replaceFirstChar { it.uppercase() }) },
                            onClick = { priority = opt; priorityExpanded = false }
                        )
                    }
                }
            }
            Spacer(Modifier.height(8.dp))

            OutlinedTextField(
                value = reminderMin, onValueChange = { reminderMin = it },
                label = { Text("Reminder (minutes before)") },
                modifier = Modifier.fillMaxWidth(),
                singleLine = true
            )
            Spacer(Modifier.height(8.dp))

            OutlinedTextField(
                value = notes, onValueChange = { notes = it },
                label = { Text("Notes") },
                modifier = Modifier.fillMaxWidth(),
                minLines = 2, maxLines = 4
            )
            Spacer(Modifier.height(16.dp))

            Row(
                modifier = Modifier.fillMaxWidth(),
                horizontalArrangement = Arrangement.spacedBy(8.dp)
            ) {
                OutlinedButton(onClick = onDismiss, modifier = Modifier.weight(1f)) {
                    Text("Cancel")
                }
                Button(
                    onClick = {
                        saving = true
                        scope.launch {
                            try {
                                val st = startTime.takeIf { it.isNotEmpty() && !allDay }?.let { "$it:00" }
                                val et = endTime.takeIf { it.isNotEmpty() && !allDay }?.let { "$it:00" }
                                val rec = recurrence.takeIf { it != "none" }
                                val pri = priority.takeIf { it.isNotEmpty() }
                                val rm = reminderMin.toIntOrNull()

                                if (isEdit) {
                                    ApiClient.getApiService().updateCalendarEvent(
                                        editEvent!!.id,
                                        CalendarEventUpdateRequest(
                                            title = title,
                                            description = desc.ifEmpty { null },
                                            category = category,
                                            eventDate = eventDate,
                                            startTime = st, endTime = et,
                                            allDay = allDay,
                                            recurrence = rec,
                                            location = location.ifEmpty { null },
                                            reminderMinutes = rm,
                                            priority = pri,
                                            notes = notes.ifEmpty { null }
                                        )
                                    )
                                } else {
                                    ApiClient.getApiService().createCalendarEvent(
                                        CalendarEventRequest(
                                            title = title,
                                            description = desc.ifEmpty { null },
                                            category = category,
                                            eventDate = eventDate,
                                            startTime = st, endTime = et,
                                            allDay = allDay,
                                            recurrence = rec,
                                            location = location.ifEmpty { null },
                                            reminderMinutes = rm,
                                            priority = pri,
                                            notes = notes.ifEmpty { null }
                                        )
                                    )
                                }
                                onSaved()
                            } catch (e: Exception) {
                                Toast.makeText(context, ErrorUtil.userMessage(e), Toast.LENGTH_SHORT).show()
                                saving = false
                            }
                        }
                    },
                    modifier = Modifier.weight(1f),
                    enabled = !saving && title.isNotEmpty()
                ) {
                    Text(if (isEdit) "Save" else "Create")
                }
            }
            Spacer(Modifier.height(32.dp))
        }
    }
}
