package com.example.dp_app

import android.graphics.Color
import android.os.Bundle
import android.view.LayoutInflater
import android.view.View
import android.view.ViewGroup
import android.widget.Button
import android.widget.EditText
import android.widget.TextView
import androidx.fragment.app.Fragment
import androidx.fragment.app.viewModels

class SensorFragment : Fragment() {

    private val sensorViewModel: SensorViewModel by viewModels()

    private lateinit var statusText: TextView
    private lateinit var startButton: Button
    private lateinit var stopButton: Button
    private lateinit var idInput: EditText

    override fun onCreateView(
        inflater: LayoutInflater,
        container: ViewGroup?,
        savedInstanceState: Bundle?
    ): View {

        val view = inflater.inflate(R.layout.fragment_sensor, container, false)

        statusText = view.findViewById(R.id.status_text)
        startButton = view.findViewById(R.id.start_button)
        stopButton = view.findViewById(R.id.stop_button)
        idInput = view.findViewById(R.id.idInput)

        sensorViewModel.init(requireContext())

        sensorViewModel.status.observe(viewLifecycleOwner) {
            statusText.text = it
        }

        sensorViewModel.isLogging.observe(viewLifecycleOwner) { isLogging ->
            startButton.isEnabled = !isLogging
            stopButton.isEnabled = isLogging

            if (isLogging) {
                startButton.setBackgroundColor(Color.parseColor("#B0BEC5"))
                stopButton.setBackgroundColor(Color.parseColor("#4CAF50"))
            } else {
                startButton.setBackgroundColor(Color.parseColor("#4CAF50"))
                stopButton.setBackgroundColor(Color.parseColor("#B0BEC5"))
            }
        }

        startButton.setOnClickListener {
            sensorViewModel.desiredFilename = idInput.text.toString()
            sensorViewModel.startLogging()
        }

        stopButton.setOnClickListener {
            sensorViewModel.stopLogging()
        }

        return view
    }
}


