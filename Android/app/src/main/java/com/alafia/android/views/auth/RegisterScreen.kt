package com.alafia.android.views.auth

import android.widget.Toast
import com.alafia.android.util.ErrorUtil
import com.alafia.android.schemas.SignupStartRequest
import com.alafia.android.schemas.SignupEmailBody
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
    var phone by remember { mutableStateOf("") }
    // Two-step signup: details, then confirm the email, THEN the account.
    // Payment is not taken here — Play Billing needs an account to attach a
    // purchase token to, so the paywall is the screen after this one.
    var awaitingVerification by remember { mutableStateOf(false) }
    var checking by remember { mutableStateOf(false) }
    var notice by remember { mutableStateOf<String?>(null) }
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
        // "We emailed you a link." The app cannot read the mailbox, so it ASKS
        // the server whether the address is confirmed rather than guessing.
        if (awaitingVerification) {
            Text("Confirm your email", style = MaterialTheme.typography.titleLarge)
            Spacer(Modifier.height(8.dp))
            Text(
                "We sent a link to $email. Open it, then come back and tap Continue.",
                style = MaterialTheme.typography.bodyMedium,
            )
            notice?.let {
                Spacer(Modifier.height(8.dp))
                Text(it, style = MaterialTheme.typography.bodySmall,
                     color = MaterialTheme.colorScheme.onSurfaceVariant)
            }
            Spacer(Modifier.height(16.dp))
            Button(
                onClick = {
                    checking = true
                    scope.launch {
                        try {
                            val api = ApiClient.getApiService()
                            val status = api.signupStatus(email)
                            if (status.emailVerified) {
                                // Creates the account and signs in. It is
                                // created UNPAID, so the paywall follows.
                                api.signupCompleteMobile(SignupEmailBody(email))
                                val login = loginWithCsrf(api, email, password)
                                KeychainHelper.saveToken(context, login.access_token)
                                val user = api.getCurrentUser()
                                KeychainHelper.saveUserId(context, user.id.toString())
                                KeychainHelper.saveUsername(context, user.email)
                                onRegisterSuccess()
                                navController.navigate("main") {
                                    popUpTo("register") { inclusive = true }
                                }
                            } else {
                                notice = "Not confirmed yet. Check your inbox, and your spam folder."
                            }
                        } catch (e: Exception) {
                            Toast.makeText(context, ErrorUtil.userMessage(e), Toast.LENGTH_LONG).show()
                        } finally {
                            checking = false
                        }
                    }
                },
                enabled = !checking,
                modifier = Modifier.fillMaxWidth().height(48.dp),
            ) {
                if (checking) {
                    CircularProgressIndicator(
                        modifier = Modifier.size(24.dp),
                        color = MaterialTheme.colorScheme.onPrimary,
                    )
                } else {
                    Text("I've confirmed — continue")
                }
            }
            TextButton(onClick = {
                scope.launch {
                    try {
                        ApiClient.getApiService().signupResend(SignupEmailBody(email))
                        notice = "Sent. It can take a minute to arrive."
                    } catch (e: Exception) {
                        Toast.makeText(context, ErrorUtil.userMessage(e), Toast.LENGTH_LONG).show()
                    }
                }
            }) { Text("Send the email again") }
            TextButton(onClick = { awaitingVerification = false }) { Text("Change my details") }
            return@Column
        }


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

        OutlinedTextField(
            value = phone,
            onValueChange = { phone = it },
            label = { Text("Phone Number (optional — enables phone login)") },
            placeholder = { Text("+1 555 123 4567") },
            singleLine = true,
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
                    firstName.trim().length >= 3 && lastName.trim().length >= 3 &&
                    DOB_PATTERN.matches(dateOfBirth)
                ) {
                    isLoading = true
                    scope.launch {
                        try {
                            // Two-step: this only sends the verification email.
                            // The account does not exist until the address is
                            // confirmed, which is the gate /auth/register never
                            // had — it created a loginable account for anything
                            // anyone typed, with no email to explain itself.
                            ApiClient.getApiService().signupStart(
                                SignupStartRequest(
                                    email = email,
                                    password = password,
                                    first_name = firstName.trim(),
                                    last_name = lastName.trim(),
                                    // An empty field is absence, not a phone
                                    // number of "": sending "" would occupy the
                                    // column and make the account unfindable by
                                    // the phone-login lookup.
                                    phone = phone.trim().ifBlank { null },
                                    date_of_birth = dateOfBirth,
                                    country = java.util.Locale.getDefault().country
                                        .ifBlank { null },
                                )
                            )
                            awaitingVerification = true
                            notice = null
                        } catch (e: Exception) {
                            Toast.makeText(context, ErrorUtil.userMessage(e), Toast.LENGTH_LONG).show()
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
                    password.isNotEmpty() &&
                    // Same rule the API enforces, so the button is disabled
                    // rather than the request refused.
                    firstName.trim().length >= 3 && lastName.trim().length >= 3
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
