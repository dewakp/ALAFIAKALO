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
    var resetToken by remember { mutableStateOf("") }
    var newPassword by remember { mutableStateOf("") }
    var confirmPassword by remember { mutableStateOf("") }
    var isLoading by remember { mutableStateOf(false) }
    var step by remember { mutableStateOf("request") } // request | confirm | done
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
                                    response.reset_token?.let { resetToken = it }
                                    step = "confirm"
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

            "confirm" -> {
                OutlinedTextField(
                    value = resetToken,
                    onValueChange = { resetToken = it },
                    label = { Text("Reset Token") },
                    modifier = Modifier.fillMaxWidth().padding(bottom = 16.dp),
                    singleLine = true,
                    enabled = !isLoading
                )

                PasswordField(
                    value = newPassword,
                    onValueChange = { newPassword = it },
                    label = "New Password",
                    modifier = Modifier.fillMaxWidth().padding(bottom = 16.dp),
                    imeAction = ImeAction.Next,
                    enabled = !isLoading
                )

                PasswordField(
                    value = confirmPassword,
                    onValueChange = { confirmPassword = it },
                    label = "Confirm Password",
                    modifier = Modifier.fillMaxWidth().padding(bottom = 16.dp),
                    enabled = !isLoading
                )

                Button(
                    onClick = {
                        if (newPassword != confirmPassword) {
                            Toast.makeText(context, "Passwords do not match", Toast.LENGTH_SHORT).show()
                            return@Button
                        }
                        isLoading = true
                        scope.launch {
                            try {
                                val apiService = ApiClient.getApiService()
                                apiService.confirmPasswordReset(
                                    PasswordResetConfirm(resetToken, newPassword)
                                )
                                step = "done"
                            } catch (e: Exception) {
                                Toast.makeText(context, ErrorUtil.userMessage(e), Toast.LENGTH_SHORT).show()
                            } finally {
                                isLoading = false
                            }
                        }
                    },
                    modifier = Modifier.fillMaxWidth().height(48.dp),
                    enabled = !isLoading && resetToken.isNotEmpty() && newPassword.length >= 6 && confirmPassword.isNotEmpty()
                ) {
                    if (isLoading) CircularProgressIndicator(modifier = Modifier.size(24.dp), color = MaterialTheme.colorScheme.onPrimary)
                    else Text("Reset Password")
                }
            }

            "done" -> {
                Text(
                    text = "Password reset successfully!",
                    style = MaterialTheme.typography.bodyLarge,
                    color = MaterialTheme.colorScheme.primary,
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

        if (step != "done") {
            TextButton(
                onClick = { navController.popBackStack() },
                modifier = Modifier.padding(top = 16.dp)
            ) {
                Text("Back to Login")
            }
        }
    }
}
