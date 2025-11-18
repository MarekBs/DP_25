package com.example.dp_app.fragments

import android.os.Bundle
import android.view.LayoutInflater
import android.view.View
import android.view.ViewGroup
import android.widget.Button
import androidx.fragment.app.Fragment
import androidx.navigation.fragment.findNavController
import com.example.dp_app.R

class IntroFragment : Fragment() {

    override fun onCreateView(
        inflater: LayoutInflater,
        container: ViewGroup?,
        savedInstanceState: Bundle?
    ): View {
        val view = inflater.inflate(R.layout.fragment_intro, container, false)

        val btnSensors = view.findViewById<Button>(R.id.btn_sensors)
        val btnTouch = view.findViewById<Button>(R.id.btn_touch)
        val btnLogging = view.findViewById<Button>(R.id.btn_logging)
        val btnZoom = view.findViewById<Button>(R.id.btn_zoom)

        btnSensors.setOnClickListener {
            findNavController().navigate(R.id.action_introFragment_to_behametricsFragment)
        }

        btnTouch.setOnClickListener {
            findNavController().navigate(R.id.action_introFragment_to_behametricsTouchFragment)
        }

        btnLogging.setOnClickListener {
            findNavController().navigate(R.id.action_introFragment_to_sensorFragment)
        }

        btnZoom.setOnClickListener {
            findNavController().navigate(R.id.action_introFragment_to_cropFragment)
        }

        return view
    }
}
