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
import com.example.dp_app.models.BehametricsViewModel
import com.example.dp_app.UserSession
import com.github.chrisbanes.photoview.PhotoView
import com.google.firebase.storage.FirebaseStorage
import android.net.Uri
import java.io.File

class CropFragment : Fragment() {

    private val viewModel: BehametricsViewModel by viewModels()

    private lateinit var photoView: PhotoView
    private lateinit var statusText: TextView
    private lateinit var startButton: Button
    private lateinit var stopButton: Button
    private lateinit var backButton: Button
    private lateinit var counterText: TextView
    private lateinit var hintOverlay: View
    private lateinit var uploadOverlay: View
    private lateinit var successOverlay: View

    private var maxScale = 1f
    private var autoStopped = false
    private var isAmplifying = false

    override fun onCreateView(
        inflater: LayoutInflater,
        container: ViewGroup?,
        savedInstanceState: Bundle?
    ): View {
        return inflater.inflate(R.layout.fragment_crop, container, false)
    }

    override fun onViewCreated(view: View, savedInstanceState: Bundle?) {
        super.onViewCreated(view, savedInstanceState)

        photoView = view.findViewById(R.id.photoView)
        photoView.setImageResource(R.drawable.stvorec_zoom)

        setupPhotoView()

        statusText = view.findViewById(R.id.status_text)
        startButton = view.findViewById(R.id.start_button)
        stopButton = view.findViewById(R.id.stop_button)
        backButton = view.findViewById(R.id.back_button)
        counterText = view.findViewById(R.id.counter_text)
        hintOverlay = view.findViewById(R.id.hint_overlay)
        uploadOverlay = view.findViewById(R.id.upload_overlay)
        successOverlay = view.findViewById(R.id.success_overlay)

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
            findNavController().navigate(R.id.action_cropFragment_to_introFragment)
        }

        backButton.visibility = View.GONE
    }

    private fun setupPhotoView() {

        val drawable = resources.getDrawable(R.drawable.stvorec_zoom, null)
        val imageWidth = drawable.intrinsicWidth.toFloat()
        val imageHeight = drawable.intrinsicHeight.toFloat()

        photoView.post {
            val frameSize = minOf(photoView.width, photoView.height).toFloat()
            val scaleX = frameSize / imageWidth
            val scaleY = frameSize / imageHeight
            maxScale = maxOf(scaleX, scaleY)

            photoView.minimumScale = 1f
            photoView.maximumScale = maxScale
            photoView.setScaleLevels(1f, maxScale / 2f, maxScale)
        }

        photoView.setOnScaleChangeListener { scaleFactor, focusX, focusY ->
            if (!isAmplifying) {
                isAmplifying = true
                val amplified = 1f + (scaleFactor - 1f) * 1.2f
                val newScale = (photoView.scale * amplified).coerceIn(1f, maxScale)
                photoView.setScale(newScale, focusX, focusY, false)
                isAmplifying = false
            }
            if (!autoStopped && viewModel.isLogging.value == true && photoView.scale >= maxScale * 0.98f) {
                autoStopped = true
                stopCurrentLogging()
            }
        }
    }

    private fun resetZoom() {
        photoView.setScale(1f, false)
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

        autoStopped = false
        isAmplifying = false
        viewModel.incrementAttempt()
        statusText.text = "Logovanie..."
        viewModel.startLogging(requireActivity())
    }

    private fun stopCurrentLogging() {
        viewModel.stopLogging(requireActivity())
        resetZoom()
        photoView.isEnabled = false
        uploadOverlay.visibility = View.VISIBLE

        uploadCurrentLog {
            uploadOverlay.visibility = View.GONE
            photoView.isEnabled = true
            val attempt = viewModel.currentAttempt.value ?: 0
            if (attempt >= viewModel.maxAttempts) {
                finishAllAttempts()
            } else {
                startNextAttempt()
            }
        }
    }

    private fun finishAllAttempts() {
        startButton.isEnabled = false
        UserSession.markCompleted(requireContext(), "zoom")
        successOverlay.visibility = View.VISIBLE
        successOverlay.findViewById<android.widget.Button>(R.id.success_menu_button).setOnClickListener {
            findNavController().navigate(R.id.action_cropFragment_to_introFragment)
        }
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
        val ref = storage.reference.child("touch_zoom_behametrics/$userId/$filename")

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
