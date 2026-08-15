package com.alafia.android.views.auth

import android.widget.Toast
import androidx.compose.foundation.layout.*
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.verticalScroll
import androidx.compose.material3.*
import androidx.compose.runtime.*
import androidx.compose.ui.text.input.KeyboardType
import androidx.compose.foundation.text.KeyboardOptions
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.text.input.ImeAction
import com.alafia.android.views.components.PasswordField
import androidx.compose.ui.unit.dp
import androidx.navigation.NavHostController
import com.alafia.android.MainActivity
import com.alafia.android.api.ApiClient
import com.alafia.android.api.KeychainHelper
import com.alafia.android.api.loginWithCsrf
import com.alafia.android.schemas.RegisterRequest
import kotlinx.coroutines.launch

@Composable
fun RegisterScreen(
    navController: NavHostController,
    activity: MainActivity,
    onRegisterSuccess: () -> Unit
) {
    var email by remember { mutableStateOf("") }
    var password by remember { mutableStateOf("") }
    var confirmPassword by remember { mutableStateOf("") }
    var firstName by remember { mutableStateOf("") }
    var lastName by remember { mutableStateOf("") }
    // Required by the backend: an account holder must be an adult by their own
    // jurisdiction's standard (app/core/age_policy.py). This screen previously
    // sent date_of_birth = null, which the age gate rejects with a 422.
    var dateOfBirth by remember { mutableStateOf("") }
    var isLoading by remember { mutableStateOf(false) }
    val scope = rememberCoroutineScope()
    val context = LocalContext.current

    Column(
        modifier = Modifier
            .fillMaxSize()
            .padding(16.dp)
            .verticalScroll(rememberScrollState()),
        verticalArrangement = Arrangement.Top,
        horizontalAlignment = Alignment.CenterHorizontally
    ) {
        Text(
            text = "Create Account",
            style = MaterialTheme.typography.headlineLarge,
            modifier = Modifier.padding(vertical = 32.dp)
        )

        OutlinedTextField(
            value = firstName,
            onValueChange = { firstName = it },
            label = { Text("First Name") },
            modifier = Modifier
                .fillMaxWidth()
                .padding(bottom = 12.dp),
            enabled = !isLoading
        )

        OutlinedTextField(
            value = lastName,
            onValueChange = { lastName = it },
            label = { Text("Last Name") },
            modifier = Modifier
                .fillMaxWidth()
                .padding(bottom = 12.dp),
            enabled = !isLoading
        )

        OutlinedTextField(
            value = dateOfBirth,
            onValueChange = { dateOfBirth = it },
            label = { Text("Date of Birth (YYYY-MM-DD)") },
            placeholder = { Text("1990-01-31") },
            supportingText = {
                Text("An account holder must be an adult. A child is tracked as a " +
                     "dependent profile under a parent or guardian's account.")
            },
            keyboardOptions = KeyboardOptions(keyboardType = KeyboardType.Number),
            modifier = Modifier
                .fillMaxWidth()
                .padding(bottom = 12.dp),
            enabled = !isLoading
        )

        OutlinedTextField(
            value = email,
            onValueChange = { email = it },
            label = { Text("Email") },
            modifier = Modifier
                .fillMaxWidth()
                .padding(bottom = 12.dp),
            enabled = !isLoading
        )

        PasswordField(
            value = password,
            onValueChange = { password = it },
            modifier = Modifier
                .fillMaxWidth()
                .padding(bottom = 12.dp),
            imeAction = ImeAction.Next,
            enabled = !isLoading
        )

        PasswordField(
            value = confirmPassword,
            onValueChange = { confirmPassword = it },
            label = "Confirm Password",
            modifier = Modifier
                .fillMaxWidth()
                .padding(bottom = 24.dp),
            enabled = !isLoading
        )

        Button(
            onClick = {
                if (password != confirmPassword) {
                    Toast.makeText(context, "Passwords do not match", Toast.LENGTH_SHORT).show()
                    return@Button
                }
                
                if (email.isNotEmpty() && password.isNotEmpty() &&
                    firstName.isNotEmpty() && lastName.isNotEmpty() &&
                    DOB_PATTERN.matches(dateOfBirth)
                ) {
                    isLoading = true
                    scope.launch {
                        try {
                            val apiService = ApiClient.getApiService()
                            // Register creates the user
                            apiService.register(
                                RegisterRequest(
                                    email = email,
                                    password = password,
                                    full_name = "$firstName $lastName",
                                    date_of_birth = dateOfBirth,
                                    gender = null
                                )
                            )
                            // Login to get token
                            val loginResponse = loginWithCsrf(apiService, email, password)
                            KeychainHelper.saveToken(context, loginResponse.access_token)
                            // Fetch user profile
                            val user = apiService.getCurrentUser()
                            KeychainHelper.saveUserId(context, user.id.toString())
                            KeychainHelper.saveUsername(context, user.email)
                            onRegisterSuccess()
                            navController.navigate("main") {
                                popUpTo("register") { inclusive = true }
                            }
                        } catch (e: Exception) {
                            Toast.makeText(context, "Registration failed: ${e.message}", Toast.LENGTH_SHORT).show()
                        } finally {
                            isLoading = false
                        }
                    }
                }
            },
            modifier = Modifier
                .fillMaxWidth()
                .height(48.dp),
            enabled = !isLoading && email.isNotEmpty() &&
                    password.isNotEmpty() && firstName.isNotEmpty() && lastName.isNotEmpty()
        ) {
            if (isLoading) {
                CircularProgressIndicator(
                    modifier = Modifier.size(24.dp),
                    color = MaterialTheme.colorScheme.onPrimary
                )
            } else {
                Text("Register")
            }
        }

        TextButton(
            onClick = { navController.popBackStack() },
            modifier = Modifier.padding(top = 16.dp),
            enabled = !isLoading
        ) {
            Text("Already have an account? Login")
        }
    }
}

/** ISO `YYYY-MM-DD`, which is what the API's age gate parses. */
private val DOB_PATTERN = Regex("""\d{4}-\d{2}-\d{2}""")
