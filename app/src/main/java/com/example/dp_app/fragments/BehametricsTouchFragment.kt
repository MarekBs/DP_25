package com.example.dp_app.fragments

import android.os.Bundle
import android.view.LayoutInflater
import android.view.View
import android.view.ViewGroup
import android.widget.Button
import android.widget.TextView
import androidx.fragment.app.Fragment
import androidx.fragment.app.viewModels
import androidx.navigation.fragment.findNavController
import com.example.dp_app.R
import com.example.dp_app.UserSession
import com.example.dp_app.adapters.ImageAdapter
import com.example.dp_app.models.BehametricsViewModel
import com.google.firebase.storage.FirebaseStorage
import android.net.Uri
import androidx.viewpager2.widget.ViewPager2
import java.io.File

class BehametricsTouchFragment : Fragment() {

    private val viewModel: BehametricsViewModel by viewModels()

    private lateinit var statusText: TextView
    private lateinit var startButton: Button
    private lateinit var stopButton: Button
    private lateinit var backButton: Button
    private lateinit var counterText: TextView
    private lateinit var hintOverlay: View

    override fun onCreateView(
        inflater: LayoutInflater,
        container: ViewGroup?,
        savedInstanceState: Bundle?
    ): View {
        return inflater.inflate(R.layout.fragment_touch, container, false)
    }

    override fun onViewCreated(view: View, savedInstanceState: Bundle?) {
        super.onViewCreated(view, savedInstanceState)

        statusText = view.findViewById(R.id.status_text)
        startButton = view.findViewById(R.id.start_button)
        stopButton = view.findViewById(R.id.stop_button)
        backButton = view.findViewById(R.id.back_button)
        counterText = view.findViewById(R.id.counter_text)
        hintOverlay = view.findViewById(R.id.hint_overlay)

        viewModel.init(requireContext())

        viewModel.status.observe(viewLifecycleOwner) {
            statusText.text = it
        }

        viewModel.currentAttempt.observe(viewLifecycleOwner) { attempt ->
            counterText.text = "$attempt / ${viewModel.maxAttempts}"
            startButton.isEnabled = !(viewModel.isLogging.value ?: false) && attempt < viewModel.maxAttempts
        }

        viewModel.isLogging.observe(viewLifecycleOwner) { logging ->
            val attempt = viewModel.currentAttempt.value ?: 0
            startButton.isEnabled = !logging && attempt < viewModel.maxAttempts
            stopButton.isEnabled = logging
        }

        startButton.setOnClickListener {
            startNextAttempt()
        }

        stopButton.setOnClickListener {
            stopCurrentLogging()
        }

        backButton.setOnClickListener {
            findNavController().navigate(R.id.action_behametricsTouchFragment_to_introFragment)
        }

        val images = listOf(
            R.drawable.num1,
            R.drawable.num2,
            R.drawable.num3,
            R.drawable.num4,
            R.drawable.num5,
            R.drawable.num6,
            R.drawable.num7,
            R.drawable.num8,
            R.drawable.num9,
            R.drawable.num10
        )

        val viewPager = view.findViewById<ViewPager2>(R.id.viewPager)
        viewPager.adapter = ImageAdapter(images)

        backButton.visibility = View.GONE
    }

    private fun startNextAttempt() {
        val attempt = viewModel.currentAttempt.value ?: 0
        if (attempt >= viewModel.maxAttempts) {
            finishAllAttempts()
            return
        }

        if (attempt == 0) {
            hintOverlay.animate().alpha(0f).setDuration(300).withEndAction {
                hintOverlay.visibility = View.GONE
            }.start()
        }

        viewModel.incrementAttempt()
        statusText.text = "Logovanie..."
        viewModel.startLogging(requireActivity())
    }

    private fun stopCurrentLogging() {
        viewModel.stopLogging(requireActivity())

        uploadCurrentLog {
            val attempt = viewModel.currentAttempt.value ?: 0
            if (attempt >= viewModel.maxAttempts) {
                finishAllAttempts()
            } else {
                statusText.text = "Pripravený na ďalší pokus"
                startButton.isEnabled = true
            }
        }
    }

    private fun finishAllAttempts() {
        statusText.text = "Hotovo!"
        backButton.visibility = View.VISIBLE
        startButton.isEnabled = false
    }

    private fun uploadCurrentLog(onComplete: () -> Unit) {
        val logDir = File(requireContext().filesDir, "logs")

        if (!logDir.exists()) {
            statusText.text = "Priečinok logov nenájdený"
            onComplete()
            return
        }

        val files = logDir.listFiles()
            ?.filter { !it.name.contains("orientation", ignoreCase = true) }
            ?: emptyList()

        if (files.isEmpty()) {
            statusText.text = "Žiadne logy"
            onComplete()
            return
        }

        statusText.text = "Nahrávanie..."

        val attempt = viewModel.currentAttempt.value ?: 0
        var uploaded = 0
        val total = files.size

        for (file in files) {
            uploadToFirebaseTouch(file, attempt) {
                uploaded++
                if (uploaded == total) {
                    onComplete()
                }
            }
        }
    }

    private fun uploadToFirebaseTouch(file: File, attemptNumber: Int, onFinish: () -> Unit) {
        val storage = FirebaseStorage.getInstance()
        val uri = Uri.fromFile(file)

        val userId = UserSession.userId
        val filename = "log${attemptNumber}_${file.name}"
        val ref = storage.reference.child("touch_gallery_behametrics/$userId/$filename")

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
