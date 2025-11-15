package com.example.dp_app

import android.os.Bundle
import android.view.LayoutInflater
import android.view.View
import android.view.ViewGroup
import android.widget.Button
import android.widget.TextView
import androidx.fragment.app.Fragment
import androidx.fragment.app.viewModels
import com.google.firebase.storage.FirebaseStorage
import android.net.Uri
import android.widget.EditText
import java.io.File

class BehametricsFragment : Fragment() {

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

        val view = inflater.inflate(R.layout.fragment_behametrics, container, false)

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
            uploadNonTouchLogs()
        }

        return view
    }

    /**
     * Upload only NON-TOUCH logs
     */
    private fun uploadNonTouchLogs() {
        val logDir = File(requireContext().filesDir, "logs")

        if (!logDir.exists()) {
            statusText.text = "❗ Logs folder not found."
            return
        }

        // filter out touch logs
        val files = logDir.listFiles()
            ?.filter { !it.name.contains("touch", ignoreCase = true) }
            ?: emptyList()

        if (files.isEmpty()) {
            statusText.text = "❗ No non-touch logs found."
            return
        }

        statusText.text = "⬆ Uploading logs..."

        var uploaded = 0
        val total = files.size

        for (file in files) {
            uploadToFirebase(file) {
                uploaded++
                if (uploaded == total) {
                    statusText.text = "✅ All non-touch logs uploaded"
                }
            }
        }
    }

    /**
     * Upload a single file
     */
    private fun uploadToFirebase(file: File, onFinish: () -> Unit) {
        val storage = FirebaseStorage.getInstance()
        val uri = Uri.fromFile(file)

        val filename = idInput.text.toString() + "_" + file.name
        val ref = storage.reference.child("sensors_logs/$filename")

        ref.putFile(uri)
            .addOnSuccessListener { onFinish() }
            .addOnFailureListener {
                statusText.text = "Upload failed: ${it.message}"
                onFinish()
            }
    }
}






