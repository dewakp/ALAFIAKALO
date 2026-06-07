package com.alafia.android.views.auth

import android.widget.Toast
import androidx.compose.foundation.layout.*
import androidx.compose.material3.*
import androidx.compose.runtime.*
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.text.input.PasswordVisualTransformation
import androidx.compose.ui.unit.dp
import androidx.navigation.NavHostController
import com.alafia.android.MainActivity
import com.alafia.android.api.ApiClient
import com.alafia.android.api.KeychainHelper
import com.alafia.android.api.loginWithCsrf
import com.alafia.android.schemas.LoginRequest
import kotlinx.coroutines.launch

@Composable
fun LoginScreen(
    navController: NavHostController,
    activity: MainActivity,
    onLoginSuccess: () -> Unit
) {
    var email by remember { mutableStateOf("") }
    var password by remember { mutableStateOf("") }
    var isLoading by remember { mutableStateOf(false) }
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
            text = "ALAFIA",
            style = MaterialTheme.typography.headlineLarge,
            modifier = Modifier.padding(bottom = 32.dp)
        )

        OutlinedTextField(
            value = email,
            onValueChange = { email = it },
            label = { Text("Email") },
            modifier = Modifier
                .fillMaxWidth()
                .padding(bottom = 16.dp),
            singleLine = true,
            enabled = !isLoading
        )

        OutlinedTextField(
            value = password,
            onValueChange = { password = it },
            label = { Text("Password") },
            modifier = Modifier
                .fillMaxWidth()
                .padding(bottom = 24.dp),
            singleLine = true,
            visualTransformation = PasswordVisualTransformation(),
            enabled = !isLoading
        )

        Button(
            onClick = {
                if (email.isNotEmpty() && password.isNotEmpty()) {
                    isLoading = true
                    scope.launch {
                        try {
                            val apiService = ApiClient.getApiService()
                            val response = loginWithCsrf(apiService, email.trim(), password.trim())
                            KeychainHelper.saveToken(context, response.access_token)
                            response.refresh_token?.let {
                                KeychainHelper.saveRefreshToken(context, it)
                            }
                            // Fetch user profile now that token is saved
                            val user = apiService.getCurrentUser()
                            KeychainHelper.saveUserId(context, user.id.toString())
                            KeychainHelper.saveUsername(context, user.email)
                            onLoginSuccess()
                            navController.navigate("main") {
                                popUpTo("login") { inclusive = true }
                            }
                        } catch (e: retrofit2.HttpException) {
                            val msg = if (e.code() == 401) "Incorrect email or password" else "Login failed: ${e.message()}"
                            Toast.makeText(context, msg, Toast.LENGTH_SHORT).show()
                        } catch (e: Exception) {
                            Toast.makeText(context, "Login failed: ${e.message}", Toast.LENGTH_SHORT).show()
                        } finally {
                            isLoading = false
                        }
                    }
                }
            },
            modifier = Modifier
                .fillMaxWidth()
                .height(48.dp),
            enabled = !isLoading && email.isNotEmpty() && password.isNotEmpty()
        ) {
            if (isLoading) {
                CircularProgressIndicator(
                    modifier = Modifier.size(24.dp),
                    color = MaterialTheme.colorScheme.onPrimary
                )
            } else {
                Text("Login")
            }
        }

        TextButton(
            onClick = { navController.navigate("forgot-password") },
            modifier = Modifier.padding(top = 8.dp),
            enabled = !isLoading
        ) {
            Text("Forgot password?")
        }

        TextButton(
            onClick = { navController.navigate("register") },
            modifier = Modifier.padding(top = 8.dp),
            enabled = !isLoading
        ) {
            Text("Don't have an account? Register")
        }
    }
}
