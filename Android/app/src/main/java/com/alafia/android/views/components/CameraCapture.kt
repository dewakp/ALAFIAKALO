package com.alafia.android.views.components

import android.Manifest
import android.content.Context
import android.content.pm.PackageManager
import android.net.Uri
import androidx.activity.compose.rememberLauncherForActivityResult
import androidx.activity.result.contract.ActivityResultContracts
import androidx.compose.runtime.Composable
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.saveable.rememberSaveable
import androidx.compose.runtime.setValue
import androidx.compose.ui.platform.LocalContext
import androidx.core.content.ContextCompat
import androidx.core.content.FileProvider
import java.io.File

/**
 * Take a photo with the CAMERA, and hand back its content:// Uri.
 *
 * Every image entry point in this app used `GetContent()`, which opens the
 * document/photo picker and nothing else — behind a camera icon. The subject of
 * each one (a meal, a medication label, a test strip) is physically in front of
 * the user at the moment they tap, so the camera is the right default and the
 * library is the exception.
 *
 * `TakePicture()` writes into a Uri the caller supplies; it cannot invent one.
 * That Uri must come from the app's FileProvider, because handing a raw file://
 * to the camera app throws FileUriExposedException on API 24+. The provider is
 * already declared and shares the cache directory, so captures go there.
 */
class CameraCaptureController internal constructor(
    private val context: Context,
    private val launchCamera: (Uri) -> Unit,
    private val requestPermission: () -> Unit,
    private val readPending: () -> String?,
    private val writePending: (String?) -> Unit,
) {
    /**
     * Where the photo is being written.
     *
     * Held in SAVED state, not in `remember`. A camera app is one of the most
     * memory-hungry things a phone runs, so it routinely causes our process to
     * be killed while it is in the foreground. The ActivityResult API restores
     * the pending request and delivers `success = true` on the way back — but a
     * `remember`ed field is gone by then, so the Uri read back was null and the
     * photo the patient had just taken was silently dropped. The failure looks
     * exactly like "the camera does nothing", and it is worst on the cheap,
     * low-memory phones most likely to be in use.
     */
    internal var pendingUri: Uri?
        get() = readPending()?.let(Uri::parse)
        set(value) = writePending(value?.toString())

    private fun newPhotoUri(): Uri {
        val dir = File(context.cacheDir, "camera").apply { mkdirs() }
        val file = File(dir, "capture_${System.currentTimeMillis()}.jpg")
        return FileProvider.getUriForFile(context, "${context.packageName}.fileprovider", file)
    }

    /** Ask for the camera, requesting permission first if it is not yet held. */
    fun capture() {
        val granted = ContextCompat.checkSelfPermission(
            context, Manifest.permission.CAMERA
        ) == PackageManager.PERMISSION_GRANTED

        if (!granted) {
            requestPermission()
            return
        }
        val uri = newPhotoUri()
        pendingUri = uri
        launchCamera(uri)
    }

    internal fun captureAfterPermission() = capture()
}

/**
 * Remembers a camera controller wired to its launchers.
 *
 * [onImage] receives the content Uri of a photo that was actually taken —
 * it is not called when the user backs out of the camera, and not called when
 * permission is refused.
 */
@Composable
fun rememberCameraCapture(onImage: (Uri) -> Unit): CameraCaptureController {
    val context = LocalContext.current
    // Survives process death; a plain `remember` does not.
    var pending by rememberSaveable { mutableStateOf<String?>(null) }
    var controller: CameraCaptureController? = null

    val cameraLauncher = rememberLauncherForActivityResult(
        ActivityResultContracts.TakePicture()
    ) { success ->
        val uri = controller?.pendingUri
        controller?.pendingUri = null
        // `success` is false when the user pressed back without shooting.
        // Reporting that as an image would upload an empty file.
        if (success && uri != null) onImage(uri)
    }

    val permissionLauncher = rememberLauncherForActivityResult(
        ActivityResultContracts.RequestPermission()
    ) { granted ->
        if (granted) controller?.captureAfterPermission()
    }

    val instance = remember {
        CameraCaptureController(
            context = context,
            launchCamera = { cameraLauncher.launch(it) },
            requestPermission = { permissionLauncher.launch(Manifest.permission.CAMERA) },
            readPending = { pending },
            writePending = { pending = it },
        )
    }
    controller = instance
    return instance
}
