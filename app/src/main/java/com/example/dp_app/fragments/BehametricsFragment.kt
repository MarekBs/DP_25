package com.example.dp_app

import android.content.Context
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
import android.view.inputmethod.InputMethodManager
import android.widget.ArrayAdapter
import android.widget.AutoCompleteTextView
import android.widget.EditText
import java.io.File

class BehametricsFragment : Fragment() {

    private val viewModel: BehametricsViewModel by viewModels()

    private lateinit var statusText: TextView
    private lateinit var startButton: Button
    private lateinit var stopButton: Button

    private lateinit var dropdown: AutoCompleteTextView

    private var selectedActivity: String = ""


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


        dropdown = view.findViewById(R.id.dropdown)

        val options = listOf("Chôdza vo vrecku", "Zdvihnutie", "Chôdza v ruke")
        val adapter = ArrayAdapter(requireContext(), android.R.layout.simple_list_item_1, options)
        dropdown.setAdapter(adapter)

        dropdown.setOnItemClickListener { parent, _, position, _ ->
            val selected = parent.getItemAtPosition(position).toString()
            // napr. uložíš si vybranú hodnotu do premennej
            selectedActivity = selected
        }


        return view
    }
    private fun hideKeyboard() {
        val imm = requireContext().getSystemService(Context.INPUT_METHOD_SERVICE) as InputMethodManager
        imm.hideSoftInputFromWindow(requireView().windowToken, 0)
    }

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
                    statusText.text = "✅ All logs uploaded"
                }
            }
        }
    }


    private fun uploadToFirebase(file: File, onFinish: () -> Unit) {
        val storage = FirebaseStorage.getInstance()
        val uri = Uri.fromFile(file)


        val filename = idInput.text.toString() + "_" + file.name
        val ref = storage.reference.child("sensors_logs_behametrics/$selectedActivity/$filename")

        ref.putFile(uri)
            .addOnSuccessListener {
                // Clear file content, keep file for next logging
                file.writeText("")
                onFinish()
            }
            .addOnFailureListener {
                statusText.text = "Upload failed: ${it.message}"
                onFinish()
            }

    }

}






