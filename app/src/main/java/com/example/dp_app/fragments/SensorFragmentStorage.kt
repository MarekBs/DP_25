package com.example.dp_app

import android.os.Build
import android.os.Bundle
import android.view.LayoutInflater
import android.view.View
import android.view.ViewGroup
import android.widget.Button
import android.widget.TextView
import androidx.annotation.RequiresApi
import androidx.fragment.app.Fragment
import androidx.fragment.app.viewModels

class SensorFragmentStorage : Fragment() {

    private lateinit var statusText: TextView
    private lateinit var startButton: Button
    private lateinit var stopButton: Button

    private val sensorViewModel: SensorViewModelStorage by viewModels()

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

        startButton.setOnClickListener {
            sensorViewModel.startLogging(
                onStart = { path ->
                    statusText.text = "📊 Logging started (50 Hz)\nFile: $path"
                },
                onStop = { msg ->
                    statusText.text = "✅ Logging stopped.\n$msg"
                }
            )
        }

        stopButton.setOnClickListener {
            if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.Q) {
                sensorViewModel.stopLogging {
                    statusText.text = "✅ Logging stopped.\n$it"
                }
            }
        }

        if (sensorViewModel.isLogging) {
            statusText.text = "📊 Logging still running..."
        }

        return view
    }
}
