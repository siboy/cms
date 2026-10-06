package id.databoks.cms

import android.content.Intent
import android.os.Bundle
import android.widget.Button
import android.widget.EditText
import android.widget.TextView
import androidx.appcompat.app.AppCompatActivity

/**
 * Pemilih perusahaan (tenant) — kunci "satu APK utk banyak perusahaan":
 * tiap perusahaan punya server/stack Docker sendiri; APK hanya perlu tahu ALAMATNYA.
 * Input: kode perusahaan (slug) -> https://<kode>.BASE_DOMAIN, atau URL lengkap (http/https).
 * Pilihan disimpan; buka berikutnya langsung ke MainActivity. Ganti perusahaan:
 * tekan-tahan ikon aplikasi -> "Ganti Perusahaan".
 */
class TenantActivity : AppCompatActivity() {
    companion object {
        // GANTI sesuai domain induk tenant-mu (subdomain per perusahaan, lihat scripts/add-tenant.sh)
        const val BASE_DOMAIN = "cms.databoks.id"
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
            val url = when {
                raw.contains("://") -> raw.trimEnd('/')
                raw.contains(".") || raw.contains(":") -> "https://${raw.trimEnd('/')}"
                else -> "https://$raw.$BASE_DOMAIN"        // kode perusahaan -> subdomain tenant
            }
            prefs.edit().putString(KEY_URL, url).apply()
            startActivity(Intent(this, MainActivity::class.java)); finish()
        }
    }
}
