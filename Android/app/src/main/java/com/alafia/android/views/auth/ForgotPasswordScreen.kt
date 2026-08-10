package com.alafia.android.views.auth
import com.alafia.android.util.ErrorUtil

import android.widget.Toast
import androidx.compose.foundation.layout.*
import androidx.compose.material3.*
import androidx.compose.runtime.*
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.text.input.ImeAction
import com.alafia.android.views.components.PasswordField
import androidx.compose.ui.unit.dp
import androidx.navigation.NavHostController
import com.alafia.android.api.ApiClient
import com.alafia.android.schemas.PasswordResetConfirm
import com.alafia.android.schemas.PasswordResetRequest
import kotlinx.coroutines.launch

@Composable
fun ForgotPasswordScreen(navController: NavHostController) {
    var email by remember { mutableStateOf("") }
    var isLoading by remember { mutableStateOf(false) }
    // No in-app confirm step: the emailed link opens the web reset page. The app
    // used to ask for a pasted reset "code", which only worked because the email
    // printed a ~200-character JWT as text.
    var step by remember { mutableStateOf("request") } // request | sent
    val scope = rememberCoroutineScope()
    val context = LocalContext.current

    Column(
        modifier = Modifier
            .fillMaxSize()
            .padding(16.dp),
        verticalArrangement = Arrangement.Center,
        horizontalAlignment = Alignment.CenterHorizontally
    ) {
        Text(
            text = "Reset Password",
            style = MaterialTheme.typography.headlineMedium,
            modifier = Modifier.padding(bottom = 24.dp)
        )

        when (step) {
            "request" -> {
                OutlinedTextField(
                    value = email,
                    onValueChange = { email = it },
                    label = { Text("Email") },
                    modifier = Modifier.fillMaxWidth().padding(bottom = 16.dp),
                    singleLine = true,
                    enabled = !isLoading
                )

                Button(
                    onClick = {
                        if (email.isNotEmpty()) {
                            isLoading = true
                            scope.launch {
                                try {
                                    val apiService = ApiClient.getApiService()
                                    val response = apiService.requestPasswordReset(
                                        PasswordResetRequest(email.trim())
                                    )
                                    step = "sent"
                                    Toast.makeText(context, response.message, Toast.LENGTH_SHORT).show()
                                } catch (e: Exception) {
                                    Toast.makeText(context, ErrorUtil.userMessage(e), Toast.LENGTH_SHORT).show()
                                } finally {
                                    isLoading = false
                                }
                            }
                        }
                    },
                    modifier = Modifier.fillMaxWidth().height(48.dp),
                    enabled = !isLoading && email.isNotEmpty()
                ) {
                    if (isLoading) CircularProgressIndicator(modifier = Modifier.size(24.dp), color = MaterialTheme.colorScheme.onPrimary)
                    else Text("Send Reset Link")
                }
            }

            "sent" -> {
                Text(
                    text = "Open the link in that email to choose a new password.",
                    style = MaterialTheme.typography.bodyLarge,
                    modifier = Modifier.padding(bottom = 8.dp)
                )
                Text(
                    text = "Your current password keeps working until you do.",
                    style = MaterialTheme.typography.bodySmall,
                    color = MaterialTheme.colorScheme.onSurfaceVariant,
                    modifier = Modifier.padding(bottom = 24.dp)
                )

                Button(
                    onClick = {
                        navController.navigate("login") {
                            popUpTo("forgot-password") { inclusive = true }
                        }
                    },
                    modifier = Modifier.fillMaxWidth().height(48.dp)
                ) {
                    Text("Back to Login")
                }
            }
        }

        if (step != "sent") {
            TextButton(
                onClick = { navController.popBackStack() },
                modifier = Modifier.padding(top = 16.dp)
            ) {
                Text("Back to Login")
            }
        }
    }
}
