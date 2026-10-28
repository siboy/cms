package team.sdrive.cms

import android.content.Intent
import android.os.Bundle
import android.widget.Button
import android.widget.EditText
import android.widget.TextView
import org.json.JSONObject
import java.net.HttpURLConnection
import java.net.URL
import java.net.URLEncoder
import kotlin.concurrent.thread
import androidx.appcompat.app.AppCompatActivity

/**
 * Pemilih perusahaan (tenant) — kunci "satu APK utk banyak perusahaan":
 * tiap perusahaan punya server/stack Docker sendiri; APK hanya perlu tahu ALAMATNYA.
 * Input: kode perusahaan -> ditanyakan ke hub https://BASE_DOMAIN/api/resolve (hasil: alamat tenant);
 * bila hub tak terjangkau, fallback ke https://<kode>.BASE_DOMAIN. Atau URL lengkap (http/https).
 * Pilihan disimpan; buka berikutnya langsung ke MainActivity. Ganti perusahaan:
 * tekan-tahan ikon aplikasi -> "Ganti Perusahaan".
 */
class TenantActivity : AppCompatActivity() {
    companion object {
        // GANTI sesuai domain induk tenant-mu (subdomain per perusahaan, lihat scripts/add-tenant.sh)
        const val BASE_DOMAIN = "sdrive.team"
        const val PREFS = "cms"; const val KEY_URL = "base_url"
    }

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        val prefs = getSharedPreferences(PREFS, MODE_PRIVATE)
        val reset = intent?.getBooleanExtra("reset", false) == true ||
                intent?.extras?.getString("reset") == "true"
        val saved = prefs.getString(KEY_URL, null)
        if (!reset && !saved.isNullOrBlank()) {            // sudah pernah pilih -> langsung masuk
            startActivity(Intent(this, MainActivity::class.java)); finish(); return
        }
        setContentView(R.layout.activity_tenant)
        val inp = findViewById<EditText>(R.id.inp)
        val err = findViewById<TextView>(R.id.err)
        if (!saved.isNullOrBlank()) inp.setText(saved)
        findViewById<Button>(R.id.go).setOnClickListener {
            val raw = inp.text.toString().trim()
            if (raw.isEmpty()) { err.text = "Isi kode perusahaan atau URL dulu"; return@setOnClickListener }
            fun enter(url: String) {
                prefs.edit().putString(KEY_URL, url).apply()
                startActivity(Intent(this, MainActivity::class.java)); finish()
            }
            when {
                raw.contains("://") -> enter(raw.trimEnd('/'))
                raw.contains(".") || raw.contains(":") -> enter("https://${raw.trimEnd('/')}")
                else -> {                                   // kode perusahaan -> tanya hub
                    val btn = it as Button
                    btn.isEnabled = false; err.text = "Memeriksa kode…"
                    thread {
                        val res = resolve(raw.lowercase())
                        runOnUiThread {
                            btn.isEnabled = true
                            when {
                                res == null -> { err.text = "Kode perusahaan tidak dikenal"; }
                                res.isEmpty() -> enter("https://${raw.lowercase()}.$BASE_DOMAIN")  // hub tak terjangkau
                                else -> enter(res)
                            }
                        }
                    }
                }
            }
        }
    }

    /** URL tenant dari hub; null = kode tidak dikenal (404); "" = hub tak terjangkau/error lain. */
    private fun resolve(code: String): String? = try {
        val c = URL("https://$BASE_DOMAIN/api/resolve?code=" + URLEncoder.encode(code, "UTF-8"))
            .openConnection() as HttpURLConnection
        c.connectTimeout = 8000; c.readTimeout = 8000
        when (c.responseCode) {
            200 -> {
                val u = JSONObject(c.inputStream.bufferedReader().readText()).optString("url")
                if (u.startsWith("https://")) u.trimEnd('/') else ""
            }
            404 -> null
            else -> ""
        }
    } catch (e: Exception) { "" }
}
