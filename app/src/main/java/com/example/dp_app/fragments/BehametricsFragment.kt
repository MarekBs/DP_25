package com.example.dp_app.fragments

import android.media.AudioManager
import android.media.ToneGenerator
import android.os.Bundle
import android.os.Handler
import android.os.Looper
import android.view.LayoutInflater
import android.view.View
import android.view.ViewGroup
import android.widget.ArrayAdapter
import android.widget.AutoCompleteTextView
import android.widget.Button
import android.widget.TextView
import android.widget.Toast
import androidx.fragment.app.Fragment
import androidx.fragment.app.viewModels
import androidx.navigation.fragment.findNavController
import com.example.dp_app.R
import com.example.dp_app.UserSession
import com.example.dp_app.models.BehametricsViewModel
import com.google.firebase.storage.FirebaseStorage
import android.net.Uri
import java.io.File

class BehametricsFragment : Fragment() {

    private val viewModel: BehametricsViewModel by viewModels()

    private lateinit var statusText: TextView
    private lateinit var startButton: Button
    private lateinit var stopButton: Button
    private lateinit var backButton: Button
    private lateinit var counterText: TextView
    private lateinit var dropdown: AutoCompleteTextView
    private lateinit var instructionText: TextView
    private lateinit var uploadOverlay: View
    private lateinit var successOverlay: View

    private lateinit var tone: ToneGenerator
    private val handler = Handler(Looper.getMainLooper())
    private var autoStopRunnable: Runnable? = null
    private val activityDuration = 3000L

    override fun onCreateView(
        inflater: LayoutInflater,
        container: ViewGroup?,
        savedInstanceState: Bundle?
    ): View {

        val view = inflater.inflate(R.layout.fragment_behametrics, container, false)

        statusText = view.findViewById(R.id.status_text)
        startButton = view.findViewById(R.id.start_button)
        stopButton = view.findViewById(R.id.stop_button)
        backButton = view.findViewById(R.id.back_button)
        counterText = view.findViewById(R.id.counter_text)
        dropdown = view.findViewById(R.id.dropdown)
        instructionText = view.findViewById(R.id.instruction_text)
        uploadOverlay = view.findViewById(R.id.upload_overlay)
        successOverlay = view.findViewById(R.id.success_overlay)

        viewModel.init(requireContext())
        tone = ToneGenerator(AudioManager.STREAM_NOTIFICATION, 100)

        viewModel.status.observe(viewLifecycleOwner) {
            statusText.text = it
        }

        viewModel.currentAttempt.observe(viewLifecycleOwner) { attempt ->
            counterText.text = "$attempt / ${viewModel.maxAttempts}"
            startButton.isEnabled = !(viewModel.isLogging.value ?: false) && attempt < viewModel.maxAttempts
            dropdown.isEnabled = attempt == 0
        }

        viewModel.isLogging.observe(viewLifecycleOwner) { logging ->
            val attempt = viewModel.currentAttempt.value ?: 0
            startButton.isEnabled = !logging && attempt < viewModel.maxAttempts
            stopButton.isEnabled = logging
        }

        viewModel.selectedActivity.observe(viewLifecycleOwner) { activity ->
            if (activity.isNotBlank() && dropdown.text.toString() != activity) {
                dropdown.setText(activity, false)
            }
        }

        val options = listOf("Položenie na stôl", "Zdvihnutie k uchu")
        val adapter = ArrayAdapter(requireContext(), android.R.layout.simple_list_item_1, options)
        dropdown.setAdapter(adapter)

        dropdown.setOnItemClickListener { parent, _, position, _ ->
            val selected = parent.getItemAtPosition(position).toString()
            viewModel.setSelectedActivity(selected)
            val instructions = when (selected) {
                "Položenie na stôl" ->
                    "Trvanie: ~3 sekundy – zastaví sa automaticky\nGesto: položte zariadenie obrazovkou nahor na rovnú plochu\nVýchodzia poloha: zariadenie držte v ruke, potom ho plynulo položte"
                "Zdvihnutie k uchu" ->
                    "Trvanie: ~3 sekundy – zastaví sa automaticky\nGesto: zdvihnite zariadenie k uchu plynulým pohybom\nVýchodzia poloha: zariadenie držte pred sebou"
                else -> ""
            }
            instructionText.text = instructions
            instructionText.visibility = if (instructions.isNotEmpty()) android.view.View.VISIBLE else android.view.View.GONE
        }

        startButton.setOnClickListener {
            if (viewModel.selectedActivity.value.isNullOrBlank()) {
                Toast.makeText(requireContext(), "Najskôr vyberte aktivitu.", Toast.LENGTH_SHORT).show()
                return@setOnClickListener
            }
            startNextAttempt()
        }

        stopButton.setOnClickListener {
            stopCurrentLogging()
        }

        backButton.setOnClickListener {
            findNavController().navigate(R.id.action_behametricsFragment_to_introFragment)
        }

        backButton.visibility = View.GONE

        return view
    }

    private fun startNextAttempt() {
        val attempt = viewModel.currentAttempt.value ?: 0
        if (attempt >= viewModel.maxAttempts) {
            finishAllAttempts()
            return
        }

        viewModel.incrementAttempt()
        statusText.text = "Prebieha záznam..."
        dropdown.isEnabled = false
        tone.startTone(ToneGenerator.TONE_PROP_BEEP, 200)
        viewModel.startLogging(requireActivity())

        autoStopRunnable = Runnable { stopCurrentLogging() }
        handler.postDelayed(autoStopRunnable!!, activityDuration)
    }

    private fun stopCurrentLogging() {
        autoStopRunnable?.let { handler.removeCallbacks(it) }
        viewModel.stopLogging(requireActivity())
        tone.startTone(ToneGenerator.TONE_PROP_BEEP, 200)
        uploadOverlay.visibility = View.VISIBLE

        uploadCurrentLog {
            uploadOverlay.visibility = View.GONE
            val attempt = viewModel.currentAttempt.value ?: 0
            if (attempt >= viewModel.maxAttempts) {
                finishAllAttempts()
            } else {
                statusText.text = "Pokus uložený. Pripravený na ďalší."
                startButton.isEnabled = true
            }
        }
    }

    private fun finishAllAttempts() {
        startButton.isEnabled = false
        dropdown.isEnabled = false
        successOverlay.visibility = View.VISIBLE
        successOverlay.findViewById<android.widget.Button>(R.id.success_menu_button).setOnClickListener {
            findNavController().navigate(R.id.action_behametricsFragment_to_introFragment)
        }
    }

    private fun uploadCurrentLog(onComplete: () -> Unit) {
        val logDir = File(requireContext().filesDir, "logs")

        if (!logDir.exists()) {
            statusText.text = "Dáta záznamu neboli nájdené."
            onComplete()
            return
        }

        val files = logDir.listFiles()
            ?.filter { !it.name.contains("touch", ignoreCase = true) && !it.name.contains("orientation", ignoreCase = true) }
            ?: emptyList()

        if (files.isEmpty()) {
            statusText.text = "Žiadne záznamy na odoslanie."
            onComplete()
            return
        }

        statusText.text = "Ukladanie dát na server..."

        val attempt = viewModel.currentAttempt.value ?: 0
        var uploaded = 0
        val total = files.size

        for (file in files) {
            uploadToFirebase(file, attempt) {
                uploaded++
                if (uploaded == total) {
                    onComplete()
                }
            }
        }
    }

    private fun uploadToFirebase(file: File, attemptNumber: Int, onFinish: () -> Unit) {
        val storage = FirebaseStorage.getInstance()
        val uri = Uri.fromFile(file)

        val userId = UserSession.userId
        val activity = viewModel.selectedActivity.value ?: ""
        val filename = "log${attemptNumber}_${file.name}"
        val ref = storage.reference.child("sensors_logs_behametrics/$activity/$userId/$filename")

        ref.putFile(uri)
            .addOnSuccessListener {
                file.writeText("")
                onFinish()
            }
            .addOnFailureListener {
                statusText.text = "Chyba pri odosielaní: ${it.message}"
                onFinish()
            }
    }
}
