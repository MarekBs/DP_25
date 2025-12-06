package com.example.dp_app

import android.os.Bundle
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

    private var selectedActivity: String = ""
    private var currentAttempt = 0
    private val maxAttempts = 15

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

        viewModel.init(requireContext())

        viewModel.status.observe(viewLifecycleOwner) {
            statusText.text = it
        }

        viewModel.isLogging.observe(viewLifecycleOwner) { logging ->
            startButton.isEnabled = !logging && currentAttempt < maxAttempts
            stopButton.isEnabled = logging
        }

        val options = listOf("Chôdza vo vrecku", "Zdvihnutie", "Chôdza v ruke")
        val adapter = ArrayAdapter(requireContext(), android.R.layout.simple_list_item_1, options)
        dropdown.setAdapter(adapter)

        dropdown.setOnItemClickListener { parent, _, position, _ ->
            selectedActivity = parent.getItemAtPosition(position).toString()
        }

        startButton.setOnClickListener {
            if (selectedActivity.isBlank()) {
                Toast.makeText(requireContext(), "Vyberte aktivitu", Toast.LENGTH_SHORT).show()
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
        dropdown.isEnabled = false
        viewModel.startLogging(requireActivity())
    }

    private fun stopCurrentLogging() {
        viewModel.stopLogging(requireActivity())
        
        uploadCurrentLog {
            if (currentAttempt >= maxAttempts) {
                finishAllAttempts()
            } else {
                statusText.text = "Pripravený na ďalší pokus"
                startButton.isEnabled = true
            }
        }
    }

    private fun finishAllAttempts() {
        statusText.text = "Hotovo!"
        counterText.text = "$maxAttempts / $maxAttempts"
        backButton.visibility = View.VISIBLE
        startButton.isEnabled = false
        dropdown.isEnabled = false
    }

    private fun updateCounter() {
        counterText.text = "$currentAttempt / $maxAttempts"
    }

    private fun uploadCurrentLog(onComplete: () -> Unit) {
        val logDir = File(requireContext().filesDir, "logs")

        if (!logDir.exists()) {
            statusText.text = "Priečinok logov nenájdený"
            onComplete()
            return
        }

        val files = logDir.listFiles()
            ?.filter { !it.name.contains("touch", ignoreCase = true) }
            ?: emptyList()

        if (files.isEmpty()) {
            statusText.text = "Žiadne logy"
            onComplete()
            return
        }

        statusText.text = "Nahrávanie..."

        var uploaded = 0
        val total = files.size

        for (file in files) {
            uploadToFirebase(file, currentAttempt) {
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
        val filename = "${userId}_pokus${attemptNumber}_${file.name}"
        val ref = storage.reference.child("sensors_logs_behametrics/$selectedActivity/$filename")

        ref.putFile(uri)
            .addOnSuccessListener {
                file.writeText("")
                onFinish()
            }
            .addOnFailureListener {
                statusText.text = "Chyba: ${it.message}"
                onFinish()
            }
    }
}
