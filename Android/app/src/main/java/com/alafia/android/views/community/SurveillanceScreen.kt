@file:OptIn(ExperimentalMaterial3Api::class)

package com.alafia.android.views.community

import android.widget.Toast
import androidx.compose.foundation.layout.*
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.lazy.items
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.filled.*
import androidx.compose.material3.*
import androidx.compose.runtime.*
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.dp
import androidx.navigation.NavHostController
import com.alafia.android.api.ApiClient
import com.alafia.android.models.SurveillanceCountry
import com.alafia.android.models.SurveillanceDisease
import com.alafia.android.models.SurveillanceGlobal
import com.alafia.android.util.ErrorUtil
import kotlinx.coroutines.launch

/** Disease Surveillance — parity with the web page (ranked-list-first; choropleth deferred).
 *  Outward = WHO GHO / CDC NNDSS indicator; inward = de-identified ALAFIA symptom activity. */
@Composable
fun SurveillanceScreen(navController: NavHostController) {
    var diseases by remember { mutableStateOf<List<SurveillanceDisease>>(emptyList()) }
    var selectedDisease by remember { mutableStateOf("influenza") }
    var data by remember { mutableStateOf<SurveillanceGlobal?>(null) }
    var isLoading by remember { mutableStateOf(true) }
    var menuOpen by remember { mutableStateOf(false) }
    val context = LocalContext.current
    val scope = rememberCoroutineScope()

    fun loadGlobal() {
        scope.launch {
            isLoading = true
            try {
                data = ApiClient.getApiService().getSurveillanceGlobal(disease = selectedDisease)
            } catch (e: Exception) {
                Toast.makeText(context, ErrorUtil.userMessage(e), Toast.LENGTH_SHORT).show()
            }
            isLoading = false
        }
    }

    LaunchedEffect(Unit) {
        try {
            diseases = ApiClient.getApiService().getSurveillanceDiseases()
            if (diseases.none { it.id == selectedDisease }) {
                diseases.firstOrNull()?.let { selectedDisease = it.id }
            }
        } catch (_: Exception) { }
        loadGlobal()
    }

    Scaffold(
        topBar = {
            TopAppBar(
                title = { Text("Disease Surveillance") },
                navigationIcon = {
                    IconButton(onClick = { navController.popBackStack() }) {
                        Icon(Icons.Default.ArrowBack, contentDescription = "Back")
                    }
                }
            )
        }
    ) { padding ->
        Column(Modifier.fillMaxSize().padding(padding)) {
            // Disease picker
            Box(Modifier.padding(horizontal = 16.dp, vertical = 8.dp)) {
                OutlinedButton(onClick = { menuOpen = true }) {
                    val d = diseases.find { it.id == selectedDisease }
                    Text(d?.let { "${it.icon} ${it.label}" } ?: selectedDisease)
                    Icon(Icons.Default.ArrowDropDown, null)
                }
                DropdownMenu(expanded = menuOpen, onDismissRequest = { menuOpen = false }) {
                    diseases.forEach { d ->
                        DropdownMenuItem(
                            text = { Text("${d.icon} ${d.label}") },
                            onClick = {
                                selectedDisease = d.id
                                menuOpen = false
                                loadGlobal()
                            }
                        )
                    }
                }
            }

            data?.let { g ->
                Text(
                    "${g.countries.size} countries · ${g.inwardTotal} ALAFIA symptom signals",
                    style = MaterialTheme.typography.labelMedium,
                    color = MaterialTheme.colorScheme.onSurfaceVariant,
                    modifier = Modifier.padding(horizontal = 16.dp)
                )
            }

            when {
                isLoading -> Box(Modifier.fillMaxSize(), contentAlignment = Alignment.Center) {
                    CircularProgressIndicator()
                }
                data == null || data!!.countries.isEmpty() ->
                    Box(Modifier.fillMaxSize(), contentAlignment = Alignment.Center) {
                        Text("No surveillance signal for this disease yet",
                            color = MaterialTheme.colorScheme.onSurfaceVariant)
                    }
                else -> {
                    val ranked = data!!.countries.sortedByDescending {
                        (it.outward ?: 0.0) + it.inward
                    }.take(60)
                    LazyColumn(
                        contentPadding = PaddingValues(16.dp),
                        verticalArrangement = Arrangement.spacedBy(6.dp)
                    ) {
                        items(ranked, key = { it.iso2 }) { c -> CountrySignalRow(c) }
                    }
                }
            }
        }
    }
}

@Composable
private fun CountrySignalRow(c: SurveillanceCountry) {
    Card(Modifier.fillMaxWidth()) {
        Row(
            Modifier.fillMaxWidth().padding(horizontal = 14.dp, vertical = 10.dp),
            horizontalArrangement = Arrangement.SpaceBetween,
            verticalAlignment = Alignment.CenterVertically
        ) {
            Column {
                Text(c.name, style = MaterialTheme.typography.titleSmall, fontWeight = FontWeight.Bold)
                c.region?.let {
                    Text(it, style = MaterialTheme.typography.labelSmall,
                        color = MaterialTheme.colorScheme.onSurfaceVariant)
                }
            }
            Column(horizontalAlignment = Alignment.End) {
                c.outward?.let { v ->
                    Text(
                        if (v >= 1000) "%,.0f".format(v) else "%g".format(v),
                        style = MaterialTheme.typography.titleSmall
                    )
                    c.outwardYear?.let {
                        Text("WHO $it", style = MaterialTheme.typography.labelSmall,
                            color = MaterialTheme.colorScheme.onSurfaceVariant)
                    }
                }
                if (c.inward > 0) {
                    Text("${c.inward} local signals",
                        style = MaterialTheme.typography.labelSmall,
                        color = MaterialTheme.colorScheme.error)
                }
            }
        }
    }
}
