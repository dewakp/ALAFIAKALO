package com.alafia.android.views.auth

import android.widget.Toast
import retrofit2.HttpException
import com.alafia.android.AppLanguage
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
import androidx.compose.ui.res.stringResource
import com.alafia.android.R

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
    // Set when the address already has an account. Held rather than toasted:
    // this is the one refusal that needs a route forward, not a message that
    // vanishes while the person is still reading the form.
    var duplicateMessage by remember { mutableStateOf<String?>(null) }
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
            text = stringResource(R.string.create_account),
            style = MaterialTheme.typography.headlineLarge,
            modifier = Modifier.padding(vertical = 32.dp)
        )
        // "We emailed you a link." The app cannot read the mailbox, so it ASKS
        // the server whether the address is confirmed rather than guessing.
        if (awaitingVerification) {
            Text(stringResource(R.string.confirm_your_email), style = MaterialTheme.typography.titleLarge)
            Spacer(Modifier.height(8.dp))
            Text(
                stringResource(R.string.we_sent_a_link_to_open_it_then_come_back, email),
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
                                val languageChanged = AppLanguage.choose(context, user.preferred_language)
                                KeychainHelper.saveUserId(context, user.id.toString())
                                KeychainHelper.saveUsername(context, user.email)
                                onRegisterSuccess()
                                navController.navigate("main") {
                                    popUpTo("register") { inclusive = true }
                                }
                                if (languageChanged) (context as? android.app.Activity)?.recreate()
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
                    Text(stringResource(R.string.i_ve_confirmed_continue))
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
            }) { Text(stringResource(R.string.send_the_email_again)) }
            TextButton(onClick = { awaitingVerification = false }) { Text(stringResource(R.string.change_my_details)) }
            return@Column
        }


        OutlinedTextField(
            value = firstName,
            onValueChange = { firstName = it },
            label = { Text(stringResource(R.string.first_name)) },
            modifier = Modifier
                .fillMaxWidth()
                .padding(bottom = 12.dp),
            enabled = !isLoading
        )

        OutlinedTextField(
            value = lastName,
            onValueChange = { lastName = it },
            label = { Text(stringResource(R.string.last_name)) },
            modifier = Modifier
                .fillMaxWidth()
                .padding(bottom = 12.dp),
            enabled = !isLoading
        )

        OutlinedTextField(
            value = dateOfBirth,
            onValueChange = { dateOfBirth = it },
            label = { Text(stringResource(R.string.date_of_birth_yyyy_mm_dd)) },
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
            label = { Text(stringResource(R.string.email)) },
            modifier = Modifier
                .fillMaxWidth()
                .padding(bottom = 12.dp),
            enabled = !isLoading
        )

        OutlinedTextField(
            value = phone,
            onValueChange = { phone = it },
            label = { Text(stringResource(R.string.phone_number_optional_enables_phone)) },
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
            label = stringResource(R.string.confirm_password),
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
                            // A duplicate address INTERRUPTS. A Toast fades on
                            // its own and offers no way forward, which is the
                            // whole problem for the one person who already has
                            // an account and is trying to create a second one.
                            //
                            // Read the body ONCE: errorBody().string() is not
                            // re-readable, so calling two helpers on the same
                            // exception leaves the second one with nothing.
                            val message = ErrorUtil.userMessage(e)
                            if ((e as? HttpException)?.code() == 409) {
                                duplicateMessage = message
                            } else {
                                Toast.makeText(context, message, Toast.LENGTH_LONG).show()
                            }
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
                Text(stringResource(R.string.register))
            }
        }

        TextButton(
            onClick = { navController.popBackStack() },
            modifier = Modifier.padding(top = 16.dp),
            enabled = !isLoading
        ) {
            Text(stringResource(R.string.already_have_an_account_login))
        }

        // The one refusal that must not fade. Web interrupts with the same
        // message and the same way out; a Toast here would leave the person who
        // already has an account staring at the form that just refused them.
        duplicateMessage?.let { message ->
            AlertDialog(
                onDismissRequest = { duplicateMessage = null },
                title = { Text(stringResource(R.string.account_already_exists)) },
                // The server's own sentence, not a rewrite of it.
                text = { Text(message) },
                confirmButton = {
                    TextButton(onClick = {
                        duplicateMessage = null
                        navController.navigate("login")
                    }) { Text(stringResource(R.string.go_to_sign_in)) }
                },
                dismissButton = {
                    TextButton(onClick = { duplicateMessage = null }) {
                        Text(stringResource(R.string.dismiss_alert))
                    }
                },
            )
        }
    }
}

/** ISO `YYYY-MM-DD`, which is what the API's age gate parses. */
private val DOB_PATTERN = Regex("""\d{4}-\d{2}-\d{2}""")
