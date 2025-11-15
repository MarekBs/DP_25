package com.example.dp_app

import android.os.Bundle
import android.view.LayoutInflater
import android.view.View
import android.view.ViewGroup
import android.widget.Button
import android.widget.TextView
import androidx.fragment.app.Fragment
import androidx.fragment.app.viewModels

class SensorFragment : Fragment() {

    private lateinit var statusText: TextView
    private lateinit var startButton: Button
    private lateinit var stopButton: Button

    private val sensorViewModel: SensorViewModel by viewModels()

    override fun onCreateView(
        inflater: LayoutInflater,
        container: ViewGroup?,
        savedInstanceState: Bundle?
    ): View {
        val view = inflater.inflate(R.layout.fragment_sensor, container, false)
        statusText = view.findViewById(R.id.status_text)
        startButton = view.findViewById(R.id.start_button)
        stopButton = view.findViewById(R.id.stop_button)

        sensorViewModel.init(requireContext())

        var fileName = view.findViewById<TextView>(R.id.user_id_input)

        startButton.setOnClickListener {

            // ⭐ TU NASTAVÍŠ NÁZOV SÚBORU
            sensorViewModel.desiredFilename = fileName.text.toString()
            // alebo: sensorViewModel.desiredFilename = filenameInput.text.toString()

            sensorViewModel.startLogging()
            statusText.text = "📊 Logging started (50 Hz)"
        }

        stopButton.setOnClickListener {
            sensorViewModel.stopLogging()
            statusText.text = "✅ Logging stopped."
        }

        if (sensorViewModel.isLogging) {
            statusText.text = "📊 Logging in progress..."
        }

        return view
    }

    override fun onDestroyView() {
        super.onDestroyView()
    }
}

