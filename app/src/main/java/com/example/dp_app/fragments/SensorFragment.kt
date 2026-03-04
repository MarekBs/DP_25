package com.example.dp_app.fragments

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
import com.example.dp_app.models.SensorViewModel

class SensorFragment : Fragment() {

    private val sensorViewModel: SensorViewModel by viewModels()

    private lateinit var statusText: TextView
    private lateinit var startButton: Button
    private lateinit var stopButton: Button
    private lateinit var backButton: Button
    private lateinit var counterText: TextView
    private lateinit var uploadOverlay: View
    private lateinit var successOverlay: View

    private val handler = Handler(Looper.getMainLooper())
    private var autoStopRunnable: Runnable? = null

    override fun onCreateView(
        inflater: LayoutInflater,
        container: ViewGroup?,
        savedInstanceState: Bundle?
    ): View {

        val view = inflater.inflate(R.layout.fragment_sensor, container, false)

        statusText = view.findViewById(R.id.status_text)
        startButton = view.findViewById(R.id.start_button)
        stopButton = view.findViewById(R.id.stop_button)
        backButton = view.findViewById(R.id.back_button)
        counterText = view.findViewById(R.id.counter_text)
        uploadOverlay = view.findViewById(R.id.upload_overlay)
        successOverlay = view.findViewById(R.id.success_overlay)

        sensorViewModel.init(requireContext())

        sensorViewModel.status.observe(viewLifecycleOwner) {
            statusText.text = it
        }

        sensorViewModel.currentAttempt.observe(viewLifecycleOwner) { attempt ->
            counterText.text = "$attempt / ${sensorViewModel.maxAttempts}"
            startButton.isEnabled = !(sensorViewModel.isLogging.value ?: false) && attempt < sensorViewModel.maxAttempts
        }

        sensorViewModel.isLogging.observe(viewLifecycleOwner) { isLogging ->
            val attempt = sensorViewModel.currentAttempt.value ?: 0
            startButton.isEnabled = !isLogging && attempt < sensorViewModel.maxAttempts
            stopButton.isEnabled = isLogging
        }

        sensorViewModel.isUploading.observe(viewLifecycleOwner) { uploading ->
            uploadOverlay.visibility = if (uploading) View.VISIBLE else View.GONE
        }

        startButton.setOnClickListener {
            startNextAttempt()
        }

        stopButton.setOnClickListener {
            stopCurrentLogging()
        }

        backButton.setOnClickListener {
            findNavController().navigate(R.id.action_sensorFragment_to_introFragment)
        }

        backButton.visibility = View.GONE

        return view
    }

    private fun startNextAttempt() {
        val attempt = sensorViewModel.currentAttempt.value ?: 0
        if (attempt >= sensorViewModel.maxAttempts) {
            finishAllAttempts()
            return
        }

        sensorViewModel.incrementAttempt()
        statusText.text = "Prebieha záznam..."

        sensorViewModel.desiredFilename = "log${sensorViewModel.currentAttempt.value}"
        sensorViewModel.startLogging()

        autoStopRunnable = Runnable { stopCurrentLogging() }
        handler.postDelayed(autoStopRunnable!!, 16000)
    }

    private fun stopCurrentLogging() {
        autoStopRunnable?.let { handler.removeCallbacks(it) }
        sensorViewModel.stopLogging()

        handler.postDelayed({
            val attempt = sensorViewModel.currentAttempt.value ?: 0
            if (attempt >= sensorViewModel.maxAttempts) {
                finishAllAttempts()
            } else {
                statusText.text = "Pokus uložený. Pripravený na ďalší."
                startButton.isEnabled = true
            }
        }, 2000)
    }

    private fun finishAllAttempts() {
        startButton.isEnabled = false
        UserSession.markCompleted(requireContext(), "logging")
        successOverlay.visibility = View.VISIBLE
        successOverlay.findViewById<android.widget.Button>(R.id.success_menu_button).setOnClickListener {
            findNavController().navigate(R.id.action_sensorFragment_to_introFragment)
        }
    }
}
