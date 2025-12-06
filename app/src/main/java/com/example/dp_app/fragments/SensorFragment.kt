package com.example.dp_app

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

class SensorFragment : Fragment() {

    private val sensorViewModel: SensorViewModel by viewModels()

    private lateinit var statusText: TextView
    private lateinit var startButton: Button
    private lateinit var stopButton: Button
    private lateinit var backButton: Button
    private lateinit var counterText: TextView

    private var currentAttempt = 0
    private val maxAttempts = 15

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

        sensorViewModel.init(requireContext())

        sensorViewModel.status.observe(viewLifecycleOwner) {
            statusText.text = it
        }

        sensorViewModel.isLogging.observe(viewLifecycleOwner) { isLogging ->
            startButton.isEnabled = !isLogging && currentAttempt < maxAttempts
            stopButton.isEnabled = isLogging
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
        updateCounter()

        return view
    }

    private fun startNextAttempt() {
        if (currentAttempt >= maxAttempts) {
            finishAllAttempts()
            return
        }

        currentAttempt++
        updateCounter()
        statusText.text = "Logovanie..."
        
        val userId = UserSession.userId
        sensorViewModel.desiredFilename = "${userId}_pokus${currentAttempt}"
        sensorViewModel.startLogging()
    }

    private fun stopCurrentLogging() {
        sensorViewModel.stopLogging()
        
        Handler(Looper.getMainLooper()).postDelayed({
            if (currentAttempt >= maxAttempts) {
                finishAllAttempts()
            } else {
                statusText.text = "Pripravený na ďalší pokus"
                startButton.isEnabled = true
            }
        }, 2000)
    }

    private fun finishAllAttempts() {
        statusText.text = "Hotovo!"
        counterText.text = "$maxAttempts / $maxAttempts"
        backButton.visibility = View.VISIBLE
        startButton.isEnabled = false
    }

    private fun updateCounter() {
        counterText.text = "$currentAttempt / $maxAttempts"
    }
}
