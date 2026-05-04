package com.example.dp_app.fragments

import android.media.AudioManager
import android.media.ToneGenerator
import android.os.Bundle
import android.os.Handler
import android.os.Looper
import android.view.LayoutInflater
import android.view.View
import android.view.ViewGroup
import android.widget.Button
import android.widget.TextView
import androidx.fragment.app.Fragment
import androidx.fragment.app.viewModels
import androidx.navigation.fragment.findNavController
import com.example.dp_app.R
import com.example.dp_app.UserSession
import com.example.dp_app.models.BehametricsViewModel
import com.google.android.material.button.MaterialButton
import org.json.JSONObject
import java.io.File
import java.net.HttpURLConnection
import java.net.URL

class VerifyPickupFragment : Fragment() {

    private val SERVER_URL = "http://192.168.1.109:5000/verify/zdvihnutie"

    private val RECORD_DURATION_MS = 3000L

    private val viewModel: BehametricsViewModel by viewModels()
    private val handler = Handler(Looper.getMainLooper())

    private lateinit var btnStart: MaterialButton
    private lateinit var btnBack: Button
    private lateinit var tvStatus: TextView
    private lateinit var tvUserId: TextView
    private lateinit var tvOverlayMsg: TextView
    private lateinit var cardResult: View
    private lateinit var overlayLoading: View
    private lateinit var tvResultIcon: TextView
    private lateinit var tvResultLabel: TextView
    private lateinit var tvResultConfidence: TextView
    private lateinit var tone: ToneGenerator

    override fun onCreateView(
        inflater: LayoutInflater, container: ViewGroup?, savedInstanceState: Bundle?
    ): View {
        val view = inflater.inflate(R.layout.fragment_verify_pickup, container, false)

        btnStart = view.findViewById(R.id.btn_start)
        btnBack = view.findViewById(R.id.btn_back)
        tvStatus = view.findViewById(R.id.tv_status)
        tvUserId = view.findViewById(R.id.tv_user_id)
        tvOverlayMsg = view.findViewById(R.id.tv_overlay_msg)
        cardResult = view.findViewById(R.id.card_result)
        overlayLoading = view.findViewById(R.id.overlay_loading)
        tvResultIcon = view.findViewById(R.id.tv_result_icon)
        tvResultLabel = view.findViewById(R.id.tv_result_label)
        tvResultConfidence = view.findViewById(R.id.tv_result_confidence)

        tvUserId.text = "Prihlásený: ${UserSession.userId}"
        tone = ToneGenerator(AudioManager.STREAM_NOTIFICATION, 100)

        viewModel.init(requireContext())

        btnStart.setOnClickListener { startVerification() }
        btnBack.setOnClickListener {
            findNavController().navigate(R.id.action_verifyPickupFragment_to_introFragment)
        }

        return view
    }

    private fun startVerification() {
        btnStart.isEnabled = false
        cardResult.visibility = View.GONE
        clearLogs()

        tvStatus.text = "Nahrávanie... (3s)"
        overlayLoading.visibility = View.VISIBLE
        tvOverlayMsg.text = "Nahráva sa gesto..."

        tone.startTone(ToneGenerator.TONE_PROP_BEEP, 200)
        viewModel.startLogging(requireActivity())

        handler.postDelayed({
            stopAndVerify()
        }, RECORD_DURATION_MS)
    }

    private fun stopAndVerify() {
        viewModel.stopLogging(requireActivity())
        tone.startTone(ToneGenerator.TONE_PROP_BEEP, 200)
        tvOverlayMsg.text = "Overujem..."
        tvStatus.text = "Odosielam na server..."

        val logDir = File(requireContext().filesDir, "logs")
        val files = logDir.listFiles()
            ?.filter { !it.name.contains("touch", ignoreCase = true) && !it.name.contains("orientation", ignoreCase = true) }
            ?: emptyList()

        val accelFile = files.firstOrNull { it.name.contains("accelerometer", ignoreCase = true) }
        val gyroFile = files.firstOrNull { it.name.contains("gyroscope", ignoreCase = true) }

        if (accelFile == null || gyroFile == null) {
            overlayLoading.visibility = View.GONE
            tvStatus.text = "Chyba: nenájdené CSV súbory (accel/gyro)"
            btnStart.isEnabled = true
            return
        }

        val userId = UserSession.userId
        val accelCsv = accelFile.readText()
        val gyroCsv = gyroFile.readText()

        Thread {
            val result = callServer(userId, accelCsv, gyroCsv)
            requireActivity().runOnUiThread { showResult(result) }
        }.start()
    }

    private fun callServer(userId: String, accelCsv: String, gyroCsv: String): ServerResult {
        return try {
            val body = JSONObject().apply {
                put("user_id", userId)
                put("accel_csv", accelCsv)
                put("gyro_csv", gyroCsv)
            }.toString()

            val conn = URL(SERVER_URL).openConnection() as HttpURLConnection
            conn.requestMethod = "POST"
            conn.setRequestProperty("Content-Type", "application/json")
            conn.connectTimeout = 5000
            conn.readTimeout = 10000
            conn.doOutput = true
            conn.outputStream.use { it.write(body.toByteArray(Charsets.UTF_8)) }

            val code = conn.responseCode
            val stream = if (code == 200) conn.inputStream else conn.errorStream
            val responseText = stream.bufferedReader().readText()
            val json = JSONObject(responseText)

            if (code == 200) {
                ServerResult(
                    authenticated = json.getBoolean("authenticated"),
                    confidence = json.getDouble("confidence"),
                    threshold = json.getDouble("threshold"),
                    error = null
                )
            } else {
                ServerResult(error = json.optString("error", "HTTP $code"))
            }
        } catch (e: Exception) {
            ServerResult(error = "Chyba spojenia: ${e.message}")
        }
    }

    private fun showResult(result: ServerResult) {
        overlayLoading.visibility = View.GONE
        btnStart.isEnabled = true

        if (result.error != null) {
            tvStatus.text = result.error
            return
        }

        cardResult.visibility = View.VISIBLE
        tvStatus.text = "Hotovo"

        if (result.authenticated) {
            tvResultIcon.text = "✓"
            tvResultIcon.setBackgroundResource(R.drawable.check_circle_bg)
            tvResultIcon.backgroundTintList = android.content.res.ColorStateList.valueOf(resources.getColor(R.color.completed_green, null))
            tvResultLabel.text = "Autentifikovaný"
            tvResultLabel.setTextColor(resources.getColor(R.color.completed_green, null))
        } else {
            tvResultIcon.text = "✗"
            tvResultIcon.setBackgroundResource(R.drawable.check_circle_bg)
            tvResultIcon.backgroundTintList = android.content.res.ColorStateList.valueOf(resources.getColor(R.color.logout_red, null))
            tvResultLabel.text = "Odmietnutý"
            tvResultLabel.setTextColor(resources.getColor(R.color.logout_red, null))
        }

        val pct = (result.confidence * 100).toInt()
        val thr = (result.threshold * 100).toInt()
        tvResultConfidence.text = "Skóre: $pct %  (prah: $thr %)"
    }

    private fun clearLogs() {
        val logDir = File(requireContext().filesDir, "logs")
        logDir.listFiles()?.forEach { it.writeText("") }
    }

    override fun onDestroyView() {
        super.onDestroyView()
        handler.removeCallbacksAndMessages(null)
        tone.release()
    }

    private data class ServerResult(
        val authenticated: Boolean = false,
        val confidence: Double = 0.0,
        val threshold: Double = 0.0,
        val error: String? = null
    )
}
