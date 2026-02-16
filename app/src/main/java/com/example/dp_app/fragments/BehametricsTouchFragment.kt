package com.example.dp_app

import android.os.Bundle
import android.view.LayoutInflater
import android.view.View
import android.view.ViewGroup
import android.widget.Button
import android.widget.TextView
import androidx.fragment.app.Fragment
import androidx.fragment.app.viewModels
import androidx.navigation.fragment.findNavController
import com.google.firebase.storage.FirebaseStorage
import android.net.Uri
import com.example.dp_app.adapters.ImageAdapter
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

    private var currentAttempt = 0
    private val maxAttempts = 15

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

        viewModel.isLogging.observe(viewLifecycleOwner) { logging ->
            startButton.isEnabled = !logging && currentAttempt < maxAttempts
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
            R.drawable.num5
        )

        val viewPager = view.findViewById<ViewPager2>(R.id.viewPager)
        viewPager.adapter = ImageAdapter(images)

        backButton.visibility = View.GONE
        updateCounter()
    }

    private fun startNextAttempt() {
        if (currentAttempt >= maxAttempts) {
            finishAllAttempts()
            return
        }

        if (currentAttempt == 0) {
            hintOverlay.animate().alpha(0f).setDuration(300).withEndAction {
                hintOverlay.visibility = View.GONE
            }.start()
        }

        currentAttempt++
        updateCounter()
        statusText.text = "Logovanie..."
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
            ?.filter { it.name.contains("touch", ignoreCase = true) }
            ?: emptyList()

        if (files.isEmpty()) {
            statusText.text = "Žiadne dotykové logy"
            onComplete()
            return
        }

        statusText.text = "Nahrávanie..."

        var uploaded = 0
        val total = files.size

        for (file in files) {
            uploadToFirebaseTouch(file, currentAttempt) {
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
        val filename = "${userId}_pokus${attemptNumber}_${file.name}"
        val ref = storage.reference.child("touch_gallery_behametrics/$filename")

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
