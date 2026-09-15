package com.alafia.android.views.privacy

import android.widget.Toast
import androidx.compose.foundation.layout.*
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.verticalScroll
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.filled.ArrowBack
import androidx.compose.material3.*
import androidx.compose.runtime.*
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.unit.dp
import androidx.navigation.NavHostController
import com.alafia.android.api.ApiClient
import com.alafia.android.models.PrivacySettings
import kotlinx.coroutines.launch
import androidx.compose.ui.res.stringResource
import com.alafia.android.R

@OptIn(ExperimentalMaterial3Api::class)
@Composable
fun PrivacySettingsScreen(
    navController: NavHostController
) {
    var settings by remember { mutableStateOf<PrivacySettings?>(null) }
    var isLoading by remember { mutableStateOf(true) }
    var showDeleteDialog by remember { mutableStateOf(false) }
    var showExportDialog by remember { mutableStateOf(false) }
    val scope = rememberCoroutineScope()
    val context = LocalContext.current

    // Load settings on initial composition
    LaunchedEffect(Unit) {
        try {
            val apiService = ApiClient.getApiService()
            settings = apiService.getPrivacySettings()
        } catch (e: Exception) {
            Toast.makeText(context, "Failed to load settings: ${e.message}", Toast.LENGTH_SHORT).show()
        } finally {
            isLoading = false
        }
    }

    fun updateSetting(key: String, value: Any) {
        scope.launch {
            try {
                val apiService = ApiClient.getApiService()
                val updatedSettings = apiService.updatePrivacySettings(mapOf(key to value))
                settings = updatedSettings
                Toast.makeText(context, "Setting updated", Toast.LENGTH_SHORT).show()
            } catch (e: Exception) {
                Toast.makeText(context, "Failed to update: ${e.message}", Toast.LENGTH_SHORT).show()
            }
        }
    }

    Scaffold(
        topBar = {
            TopAppBar(
                title = { Text(stringResource(R.string.privacy_settings)) },
                navigationIcon = {
                    IconButton(onClick = { navController.popBackStack() }) {
                        Icon(Icons.Default.ArrowBack, contentDescription = stringResource(R.string.back))
                    }
                }
            )
        }
    ) { paddingValues ->
        if (isLoading) {
            Box(
                modifier = Modifier
                    .fillMaxSize()
                    .padding(paddingValues),
                contentAlignment = Alignment.Center
            ) {
                CircularProgressIndicator()
            }
        } else {
            settings?.let { currentSettings ->
                Column(
                    modifier = Modifier
                        .fillMaxSize()
                        .padding(paddingValues)
                        .verticalScroll(rememberScrollState())
                        .padding(16.dp)
                ) {
                    // Data Sharing & Privacy Section
                    Text(
                        text = stringResource(R.string.data_sharing_privacy),
                        style = MaterialTheme.typography.titleMedium,
                        modifier = Modifier.padding(bottom = 8.dp)
                    )
                    
                    SwitchSetting(
                        title = stringResource(R.string.anonymized_analytics),
                        description = stringResource(R.string.help_improve_the_app_by_sharing),
                        checked = currentSettings.allowAnonymizedAnalytics,
                        onCheckedChange = { updateSetting("allow_anonymized_analytics", it) }
                    )
                    
                    SwitchSetting(
                        title = stringResource(R.string.collective_insights),
                        description = "Let your meal photos and corrections train ALAFIA's " +
                            "food recognition for everyone. Your photos stay with your meals " +
                            "either way — this only controls whether they improve the shared model.",
                        checked = currentSettings.allowCollectiveInsights,
                        onCheckedChange = { updateSetting("allow_collective_insights", it) }
                    )
                    
                    SwitchSetting(
                        title = stringResource(R.string.research_participation),
                        description = stringResource(R.string.allow_your_anonymized_data_to_be_used),
                        checked = currentSettings.allowResearchParticipation,
                        onCheckedChange = { updateSetting("allow_research_participation", it) }
                    )

                    Divider(modifier = Modifier.padding(vertical = 16.dp))

                    // Communications Section
                    Text(
                        text = stringResource(R.string.communications),
                        style = MaterialTheme.typography.titleMedium,
                        modifier = Modifier.padding(bottom = 8.dp)
                    )
                    
                    SwitchSetting(
                        title = stringResource(R.string.marketing_emails),
                        description = stringResource(R.string.receive_promotional_emails_and_special),
                        checked = currentSettings.allowMarketingEmails,
                        onCheckedChange = { updateSetting("allow_marketing_emails", it) }
                    )
                    
                    SwitchSetting(
                        title = stringResource(R.string.product_updates),
                        description = stringResource(R.string.receive_updates_about_new_features_and),
                        checked = currentSettings.allowProductUpdates,
                        onCheckedChange = { updateSetting("allow_product_updates", it) }
                    )
                    
                    SwitchSetting(
                        title = stringResource(R.string.health_reminders),
                        description = stringResource(R.string.receive_notifications_about_medications),
                        checked = currentSettings.allowHealthReminders,
                        onCheckedChange = { updateSetting("allow_health_reminders", it) }
                    )

                    Divider(modifier = Modifier.padding(vertical = 16.dp))

                    // AI Preferences Section
                    Text(
                        text = stringResource(R.string.ai_preferences),
                        style = MaterialTheme.typography.titleMedium,
                        modifier = Modifier.padding(bottom = 8.dp)
                    )
                    
                    SwitchSetting(
                        title = stringResource(R.string.ai_coaching),
                        description = stringResource(R.string.enable_personalized_ai_health_coaching),
                        checked = currentSettings.aiCoachingEnabled,
                        onCheckedChange = { updateSetting("ai_coaching_enabled", it) }
                    )
                    
                    SwitchSetting(
                        title = stringResource(R.string.ai_memory),
                        description = stringResource(R.string.allow_ai_to_remember_your_preferences),
                        checked = currentSettings.aiMemoryEnabled,
                        onCheckedChange = { updateSetting("ai_memory_enabled", it) }
                    )
                    
                    // AI Explainability Dropdown
                    var expandedExplainability by remember { mutableStateOf(false) }
                    val explainabilityOptions = listOf("minimal", "standard", "detailed")
                    
                    Text(
                        text = stringResource(R.string.ai_explainability_level),
                        style = MaterialTheme.typography.bodyMedium,
                        modifier = Modifier.padding(top = 8.dp, bottom = 4.dp)
                    )
                    ExposedDropdownMenuBox(
                        expanded = expandedExplainability,
                        onExpandedChange = { expandedExplainability = it }
                    ) {
                        OutlinedTextField(
                            value = currentSettings.aiExplainabilityLevel.capitalize(),
                            onValueChange = {},
                            readOnly = true,
                            trailingIcon = { ExposedDropdownMenuDefaults.TrailingIcon(expanded = expandedExplainability) },
                            modifier = Modifier
                                .fillMaxWidth()
                                .menuAnchor()
                        )
                        ExposedDropdownMenu(
                            expanded = expandedExplainability,
                            onDismissRequest = { expandedExplainability = false }
                        ) {
                            explainabilityOptions.forEach { option ->
                                DropdownMenuItem(
                                    text = { Text(option.capitalize()) },
                                    onClick = {
                                        updateSetting("ai_explainability_level", option)
                                        expandedExplainability = false
                                    }
                                )
                            }
                        }
                    }

                    Divider(modifier = Modifier.padding(vertical = 16.dp))

                    // Security Section
                    Text(
                        text = stringResource(R.string.security),
                        style = MaterialTheme.typography.titleMedium,
                        modifier = Modifier.padding(bottom = 8.dp)
                    )
                    
                    SwitchSetting(
                        title = stringResource(R.string.biometric_authentication),
                        description = stringResource(R.string.require_fingerprint_or_face_recognition),
                        checked = currentSettings.requireBiometricAuth,
                        onCheckedChange = { updateSetting("require_biometric_auth", it) }
                    )
                    
                    // Session Timeout Dropdown
                    var expandedTimeout by remember { mutableStateOf(false) }
                    val timeoutOptions = listOf(
                        15 to "15 minutes",
                        30 to "30 minutes",
                        60 to "1 hour",
                        120 to "2 hours",
                        240 to "4 hours",
                        1440 to "24 hours"
                    )
                    
                    Text(
                        text = stringResource(R.string.session_timeout),
                        style = MaterialTheme.typography.bodyMedium,
                        modifier = Modifier.padding(top = 8.dp, bottom = 4.dp)
                    )
                    ExposedDropdownMenuBox(
                        expanded = expandedTimeout,
                        onExpandedChange = { expandedTimeout = it }
                    ) {
                        OutlinedTextField(
                            value = timeoutOptions.find { it.first == currentSettings.sessionTimeoutMinutes }?.second ?: "${currentSettings.sessionTimeoutMinutes} minutes",
                            onValueChange = {},
                            readOnly = true,
                            trailingIcon = { ExposedDropdownMenuDefaults.TrailingIcon(expanded = expandedTimeout) },
                            modifier = Modifier
                                .fillMaxWidth()
                                .menuAnchor()
                        )
                        ExposedDropdownMenu(
                            expanded = expandedTimeout,
                            onDismissRequest = { expandedTimeout = false }
                        ) {
                            timeoutOptions.forEach { (minutes, label) ->
                                DropdownMenuItem(
                                    text = { Text(label) },
                                    onClick = {
                                        updateSetting("session_timeout_minutes", minutes)
                                        expandedTimeout = false
                                    }
                                )
                            }
                        }
                    }

                    Divider(modifier = Modifier.padding(vertical = 16.dp))

                    // Compliance Info Section
                    Text(
                        text = stringResource(R.string.compliance_info),
                        style = MaterialTheme.typography.titleMedium,
                        modifier = Modifier.padding(bottom = 8.dp)
                    )
                    
                    Card(
                        modifier = Modifier
                            .fillMaxWidth()
                            .padding(vertical = 8.dp),
                        colors = CardDefaults.cardColors(
                            containerColor = MaterialTheme.colorScheme.surfaceVariant
                        )
                    ) {
                        Column(modifier = Modifier.padding(16.dp)) {
                            Row(
                                modifier = Modifier.fillMaxWidth(),
                                horizontalArrangement = Arrangement.SpaceBetween
                            ) {
                                Text(stringResource(R.string.gdpr_applies))
                                Text(
                                    if (currentSettings.gdprApplies) stringResource(R.string.yes) else stringResource(R.string.no),
                                    color = if (currentSettings.gdprApplies) 
                                        MaterialTheme.colorScheme.primary 
                                    else 
                                        MaterialTheme.colorScheme.onSurfaceVariant
                                )
                            }
                            Spacer(modifier = Modifier.height(8.dp))
                            Row(
                                modifier = Modifier.fillMaxWidth(),
                                horizontalArrangement = Arrangement.SpaceBetween
                            ) {
                                Text(stringResource(R.string.hipaa_applies))
                                Text(
                                    if (currentSettings.hipaaApplies) stringResource(R.string.yes) else stringResource(R.string.no),
                                    color = if (currentSettings.hipaaApplies) 
                                        MaterialTheme.colorScheme.primary 
                                    else 
                                        MaterialTheme.colorScheme.onSurfaceVariant
                                )
                            }
                            Spacer(modifier = Modifier.height(8.dp))
                            Text(
                                stringResource(R.string.your_data_is_protected_according_to),
                                style = MaterialTheme.typography.bodySmall,
                                color = MaterialTheme.colorScheme.onSurfaceVariant
                            )
                        }
                    }

                    Divider(modifier = Modifier.padding(vertical = 16.dp))

                    // Data Rights Section
                    Text(
                        text = stringResource(R.string.data_rights),
                        style = MaterialTheme.typography.titleMedium,
                        color = MaterialTheme.colorScheme.error,
                        modifier = Modifier.padding(bottom = 8.dp)
                    )
                    
                    OutlinedButton(
                        onClick = { showExportDialog = true },
                        modifier = Modifier
                            .fillMaxWidth()
                            .padding(vertical = 4.dp)
                    ) {
                        Text(stringResource(R.string.export_my_data))
                    }
                    
                    Button(
                        onClick = { showDeleteDialog = true },
                        modifier = Modifier
                            .fillMaxWidth()
                            .padding(vertical = 4.dp),
                        colors = ButtonDefaults.buttonColors(
                            containerColor = MaterialTheme.colorScheme.error
                        )
                    ) {
                        Text(stringResource(R.string.delete_account))
                    }
                }
            }
        }
    }

    // Export Dialog
    if (showExportDialog) {
        AlertDialog(
            onDismissRequest = { showExportDialog = false },
            title = { Text(stringResource(R.string.export_data)) },
            text = { Text(stringResource(R.string.choose_export_format)) },
            confirmButton = {
                TextButton(
                    onClick = {
                        scope.launch {
                            try {
                                val apiService = ApiClient.getApiService()
                                apiService.requestDataExport("json")
                                Toast.makeText(context, "Export requested. Check back in a few minutes.", Toast.LENGTH_LONG).show()
                                showExportDialog = false
                            } catch (e: Exception) {
                                Toast.makeText(context, "Failed to request export: ${e.message}", Toast.LENGTH_SHORT).show()
                            }
                        }
                    }
                ) {
                    Text("JSON")
                }
            },
            dismissButton = {
                Row {
                    TextButton(
                        onClick = {
                            scope.launch {
                                try {
                                    val apiService = ApiClient.getApiService()
                                    apiService.requestDataExport("csv")
                                    Toast.makeText(context, "Export requested. Check back in a few minutes.", Toast.LENGTH_LONG).show()
                                    showExportDialog = false
                                } catch (e: Exception) {
                                    Toast.makeText(context, "Failed to request export: ${e.message}", Toast.LENGTH_SHORT).show()
                                }
                            }
                        }
                    ) {
                        Text("CSV")
                    }
                    TextButton(onClick = { showExportDialog = false }) {
                        Text(stringResource(R.string.cancel))
                    }
                }
            }
        )
    }

    // Delete Confirmation Dialog
    if (showDeleteDialog) {
        AlertDialog(
            onDismissRequest = { showDeleteDialog = false },
            title = { Text(stringResource(R.string.delete_account_2)) },
            text = { Text(stringResource(R.string.this_action_cannot_be_undone_all_your)) },
            confirmButton = {
                TextButton(
                    onClick = {
                        scope.launch {
                            try {
                                val apiService = ApiClient.getApiService()
                                apiService.requestAccountDeletion()
                                Toast.makeText(context, "Account deletion requested. You will be contacted for confirmation.", Toast.LENGTH_LONG).show()
                                showDeleteDialog = false
                                navController.navigate("login") {
                                    popUpTo(0) { inclusive = true }
                                }
                            } catch (e: Exception) {
                                Toast.makeText(context, "Failed to request deletion: ${e.message}", Toast.LENGTH_SHORT).show()
                            }
                        }
                    },
                    colors = ButtonDefaults.textButtonColors(
                        contentColor = MaterialTheme.colorScheme.error
                    )
                ) {
                    Text(stringResource(R.string.delete))
                }
            },
            dismissButton = {
                TextButton(onClick = { showDeleteDialog = false }) {
                    Text(stringResource(R.string.cancel))
                }
            }
        )
    }
}

@Composable
fun SwitchSetting(
    title: String,
    description: String,
    checked: Boolean,
    onCheckedChange: (Boolean) -> Unit
) {
    Row(
        modifier = Modifier
            .fillMaxWidth()
            .padding(vertical = 8.dp),
        horizontalArrangement = Arrangement.SpaceBetween,
        verticalAlignment = Alignment.CenterVertically
    ) {
        Column(modifier = Modifier.weight(1f)) {
            Text(
                text = title,
                style = MaterialTheme.typography.bodyLarge
            )
            Text(
                text = description,
                style = MaterialTheme.typography.bodySmall,
                color = MaterialTheme.colorScheme.onSurfaceVariant
            )
        }
        Switch(
            checked = checked,
            onCheckedChange = onCheckedChange
        )
    }
}
