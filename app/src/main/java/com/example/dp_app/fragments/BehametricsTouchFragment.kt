package com.example.dp_app

import android.os.Bundle
import android.view.LayoutInflater
import android.view.View
import android.view.ViewGroup
import android.widget.Button
import android.widget.EditText
import android.widget.TextView
import androidx.fragment.app.Fragment
import androidx.fragment.app.viewModels
import com.google.firebase.storage.FirebaseStorage
import android.net.Uri
import java.io.File

class BehametricsTouchFragment : Fragment() {

    private val viewModel: BehametricsViewModel by viewModels()

    private lateinit var statusText: TextView
    private lateinit var startButton: Button
    private lateinit var stopButton: Button
    private lateinit var idInput: EditText

    override fun onCreateView(
        inflater: LayoutInflater,
        container: ViewGroup?,
        savedInstanceState: Bundle?
    ): View {

        val view = inflater.inflate(R.layout.fragment_touch, container, false)

        statusText = view.findViewById(R.id.status_text)
        startButton = view.findViewById(R.id.start_button)
        stopButton = view.findViewById(R.id.stop_button)
        idInput = view.findViewById(R.id.idInput)

        viewModel.init(requireContext())

        viewModel.status.observe(viewLifecycleOwner) {
            statusText.text = it
        }

        viewModel.isLogging.observe(viewLifecycleOwner) { logging ->
            startButton.isEnabled = !logging
            stopButton.isEnabled = logging
        }

        startButton.setOnClickListener {
            viewModel.startLogging(requireActivity())
        }

        stopButton.setOnClickListener {
            viewModel.stopLogging(requireActivity())
            uploadTouchLogs()
        }

        return view
    }

    /**
     * Upload ONLY touch logs ("touch" in filename)
     */
    private fun uploadTouchLogs() {
        val logDir = File(requireContext().filesDir, "logs")
        val id = idInput.text.toString()

        if (!logDir.exists()) {
            statusText.text = "❗ Logs folder not found."
            return
        }

        // filter only touch logs
        val files = logDir.listFiles()
            ?.filter { it.name.contains("touch", ignoreCase = true) }
            ?: emptyList()

        if (files.isEmpty()) {
            statusText.text = "❗ No touch logs found."
            return
        }

        statusText.text = "⬆ Uploading touch logs..."

        var uploaded = 0
        val total = files.size

        for (file in files) {
            uploadToFirebaseTouch(file, id) {
                uploaded++
                if (uploaded == total) {
                    statusText.text = "✅ Touch logs uploaded"
                }
            }
        }
    }

    /**
     * Upload a touch log file → to touch_logs/
     */
    private fun uploadToFirebaseTouch(file: File, id: String, onFinish: () -> Unit) {
        val storage = FirebaseStorage.getInstance()
        val uri = Uri.fromFile(file)

        val filename = "${id}_${file.name}"

        val ref = storage.reference.child("touch_logs/$filename")

        ref.putFile(uri)
            .addOnSuccessListener { onFinish() }
            .addOnFailureListener {
                statusText.text = "Upload failed: ${it.message}"
                onFinish()
            }
    }
}

