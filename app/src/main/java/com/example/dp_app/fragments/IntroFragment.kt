package com.example.dp_app.fragments

import android.content.res.ColorStateList
import android.os.Bundle
import android.view.LayoutInflater
import android.view.View
import android.view.ViewGroup
import android.widget.TextView
import androidx.core.content.ContextCompat
import androidx.fragment.app.Fragment
import androidx.navigation.fragment.findNavController
import com.example.dp_app.R
import com.example.dp_app.UserSession
import com.google.android.material.button.MaterialButton

class IntroFragment : Fragment() {

    private lateinit var btnSensors: MaterialButton
    private lateinit var btnTouch: MaterialButton
    private lateinit var btnLogging: MaterialButton
    private lateinit var btnZoom: MaterialButton

    private val originalTexts = mutableMapOf<MaterialButton, String>()

    override fun onCreateView(
        inflater: LayoutInflater,
        container: ViewGroup?,
        savedInstanceState: Bundle?
    ): View {
        val view = inflater.inflate(R.layout.fragment_intro, container, false)

        view.findViewById<TextView>(R.id.user_id_text).text = "Prihlásený: ${UserSession.userId}"

        btnSensors = view.findViewById(R.id.btn_sensors)
        btnTouch = view.findViewById(R.id.btn_touch)
        btnLogging = view.findViewById(R.id.btn_logging)
        btnZoom = view.findViewById(R.id.btn_zoom)

        listOf(btnSensors, btnTouch, btnLogging, btnZoom).forEach {
            originalTexts[it] = it.text.toString()
        }

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
        view.findViewById<MaterialButton>(R.id.btn_logout).setOnClickListener {
            UserSession.clear()
            findNavController().navigate(R.id.action_introFragment_to_loginFragment)
        }

        return view
    }

    override fun onResume() {
        super.onResume()
        updateCompletionUI()
    }

    private fun updateCompletionUI() {
        val ctx = requireContext()
        val colorDone = ColorStateList.valueOf(ContextCompat.getColor(ctx, R.color.completed_green))
        val colorPartial = ColorStateList.valueOf(ContextCompat.getColor(ctx, R.color.completed_partial))
        val colorDefault = ColorStateList.valueOf(ContextCompat.getColor(ctx, R.color.accent))

        val sensorsActivities = listOf("Položenie na stôl", "Zdvihnutie k uchu")
        val sensorsDone = sensorsActivities.count { UserSession.isCompleted(ctx, "sensors_$it") }
        when (sensorsDone) {
            sensorsActivities.size -> {
                btnSensors.backgroundTintList = colorDone
                btnSensors.text = "✓  ${originalTexts[btnSensors]}"
            }
            0 -> {
                btnSensors.backgroundTintList = colorDefault
                btnSensors.text = originalTexts[btnSensors]
            }
            else -> {
                btnSensors.backgroundTintList = colorPartial
                btnSensors.text = "$sensorsDone/${sensorsActivities.size}  ${originalTexts[btnSensors]}"
            }
        }

        mapOf(
            btnTouch to "touch",
            btnLogging to "logging",
            btnZoom to "zoom"
        ).forEach { (btn, key) ->
            if (UserSession.isCompleted(ctx, key)) {
                btn.backgroundTintList = colorDone
                btn.text = "✓  ${originalTexts[btn]}"
            } else {
                btn.backgroundTintList = colorDefault
                btn.text = originalTexts[btn]
            }
        }
    }
}
