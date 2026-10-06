package id.databoks.cms

import android.annotation.SuppressLint
import android.app.DownloadManager
import android.content.Context
import android.content.Intent
import android.net.Uri
import android.os.Bundle
import android.os.Environment
import android.webkit.*
import android.widget.Toast
import androidx.activity.OnBackPressedCallback
import androidx.activity.result.contract.ActivityResultContracts
import androidx.appcompat.app.AppCompatActivity
import androidx.swiperefreshlayout.widget.SwipeRefreshLayout

/**
 * Pembungkus WebView utk aplikasi web CMS (:8879 / tenant HTTPS). Mendukung: cookie sesi persisten,
 * SSE realtime, unggah berkas/gambar dari galeri-kamera (file chooser), unduh ekspor DOCX via
 * DownloadManager, pull-to-refresh, tombol back = mundur riwayat web.
 */
class MainActivity : AppCompatActivity() {
    private lateinit var web: WebView
    private var fileCb: ValueCallback<Array<Uri>>? = null
    private val picker = registerForActivityResult(ActivityResultContracts.StartActivityForResult()) { res ->
        fileCb?.onReceiveValue(WebChromeClient.FileChooserParams.parseResult(res.resultCode, res.data))
        fileCb = null
    }

    @SuppressLint("SetJavaScriptEnabled")
    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        val base = getSharedPreferences(TenantActivity.PREFS, Context.MODE_PRIVATE)
            .getString(TenantActivity.KEY_URL, null)
        if (base.isNullOrBlank()) { startActivity(Intent(this, TenantActivity::class.java)); finish(); return }

        val swipe = SwipeRefreshLayout(this)
        web = WebView(this)
        swipe.addView(web); setContentView(swipe)
        swipe.setOnRefreshListener { web.reload() }

        web.settings.apply {
            javaScriptEnabled = true
            domStorageEnabled = true                      // localStorage: draft blok, preferensi UI
            loadsImagesAutomatically = true
            mixedContentMode = WebSettings.MIXED_CONTENT_COMPATIBILITY_MODE
            mediaPlaybackRequiresUserGesture = false
            userAgentString = "$userAgentString CMSApp/1.0"
        }
        CookieManager.getInstance().setAcceptCookie(true)
        CookieManager.getInstance().setAcceptThirdPartyCookies(web, false)

        web.webViewClient = object : WebViewClient() {
            override fun shouldOverrideUrlLoading(view: WebView, req: WebResourceRequest): Boolean {
                val u = req.url.toString()
                return if (u.startsWith(base)) false       // tetap di dalam app tenant sendiri
                else { startActivity(Intent(Intent.ACTION_VIEW, req.url)); true }  // link luar -> browser
            }
            override fun onPageFinished(view: WebView, url: String?) { swipe.isRefreshing = false }
            override fun onReceivedError(v: WebView, r: WebResourceRequest, e: WebResourceError) {
                if (r.isForMainFrame) Toast.makeText(this@MainActivity,
                    "Server tidak terjangkau — cek jaringan/VPN. Tekan-tahan ikon app utk ganti perusahaan.",
                    Toast.LENGTH_LONG).show()
            }
        }
        web.webChromeClient = object : WebChromeClient() {
            override fun onShowFileChooser(v: WebView, cb: ValueCallback<Array<Uri>>,
                                           p: FileChooserParams): Boolean {
                fileCb?.onReceiveValue(null); fileCb = cb
                picker.launch(p.createIntent()); return true
            }
        }
        web.setDownloadListener { url, ua, cd, mime, _ ->  // ekspor DOCX / unduh berkas
            val req = DownloadManager.Request(Uri.parse(url)).apply {
                addRequestHeader("Cookie", CookieManager.getInstance().getCookie(url) ?: "")
                addRequestHeader("User-Agent", ua)
                setNotificationVisibility(DownloadManager.Request.VISIBILITY_VISIBLE_NOTIFY_COMPLETED)
                setDestinationInExternalPublicDir(Environment.DIRECTORY_DOWNLOADS,
                    URLUtil.guessFileName(url, cd, mime))
            }
            (getSystemService(DOWNLOAD_SERVICE) as DownloadManager).enqueue(req)
            Toast.makeText(this, "Mengunduh…", Toast.LENGTH_SHORT).show()
        }
        onBackPressedDispatcher.addCallback(this, object : OnBackPressedCallback(true) {
            override fun handleOnBackPressed() {
                if (web.canGoBack()) web.goBack() else finish()
            }
        })
        if (savedInstanceState == null) web.loadUrl(base) else web.restoreState(savedInstanceState)
    }

    override fun onSaveInstanceState(outState: Bundle) {
        super.onSaveInstanceState(outState); web.saveState(outState)
    }
}
