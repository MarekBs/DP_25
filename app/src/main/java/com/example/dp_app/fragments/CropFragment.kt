package com.example.dp_app.fragments

import android.net.Uri
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
import com.example.dp_app.models.BehametricsViewModel
import com.github.chrisbanes.photoview.PhotoView
import com.google.firebase.storage.FirebaseStorage
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
    private lateinit var cropBorderContainer: View

    private var autoStopped = false
    private var isStopping = false
    private var computedMinScale = 0.25f
    private var computedMaxScale = 1f

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
        statusText = view.findViewById(R.id.status_text)
        startButton = view.findViewById(R.id.start_button)
        stopButton = view.findViewById(R.id.stop_button)
        backButton = view.findViewById(R.id.back_button)
        counterText = view.findViewById(R.id.counter_text)
        hintOverlay = view.findViewById(R.id.hint_overlay)
        uploadOverlay = view.findViewById(R.id.upload_overlay)
        successOverlay = view.findViewById(R.id.success_overlay)
        cropBorderContainer = view.findViewById(R.id.cropBorderContainer)

        setupPhotoView()
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
        photoView.setImageResource(R.drawable.stvorec_zoom)
        photoView.scaleType = android.widget.ImageView.ScaleType.FIT_CENTER

        photoView.post {
            val vw = photoView.width.toFloat()
            val vh = photoView.height.toFloat()
            if (vw == 0f || vh == 0f) return@post

            val drawable = photoView.drawable ?: return@post
            val iw = drawable.intrinsicWidth.toFloat()
            val ih = drawable.intrinsicHeight.toFloat()

            // Border nastavíme ako štvorec = kratšia strana PhotoView
            val borderSize = minOf(vw, vh).toInt()
            val params = cropBorderContainer.layoutParams as android.widget.FrameLayout.LayoutParams
            params.width = borderSize
            params.height = borderSize
            params.gravity = android.view.Gravity.CENTER
            cropBorderContainer.layoutParams = params

            // FIT_CENTER interne zobrazuje obraz pri tomto faktore
            val fitFactor = minOf(vw / iw, vh / ih)

            // maxScale = scale pri ktorom obraz presne vyplní štvorcový border
            // pri PhotoView scale s: zobrazená veľkosť = s * fitFactor * min(iw,ih)
            // chceme: s * fitFactor * min(iw,ih) = borderSize
            computedMinScale = 0.25f
            computedMaxScale = borderSize / (fitFactor * minOf(iw, ih))

            applyScales()
        }

        photoView.setOnScaleChangeListener { _, _, _ ->
            val currentScale = photoView.scale
            val max = photoView.maximumScale
            if (!autoStopped && viewModel.isLogging.value == true && currentScale >= max * 0.98f) {
                autoStopped = true
                stopCurrentLogging()
            }
        }
    }

    private fun applyScales() {
        val mid = (computedMinScale + computedMaxScale) / 2f
        photoView.minimumScale = computedMinScale
        photoView.mediumScale = mid
        photoView.maximumScale = computedMaxScale
        photoView.setScaleLevels(computedMinScale, mid, computedMaxScale)
        photoView.setScale(computedMinScale, false)
    }

    // Synchronný reset – spustí sa pred startLogging(), žiadna race condition
    private fun resetPhotoViewState() {
        photoView.setZoomable(false)
        photoView.setImageDrawable(null)
        photoView.setImageResource(R.drawable.stvorec_zoom)
        photoView.setZoomable(true)
        applyScales()
    }

    private fun startNextAttempt() {
        val attempt = viewModel.currentAttempt.value ?: 0
        if (attempt >= viewModel.maxAttempts) {
            finishAllAttempts()
            return
        }

        if (attempt == 0) {
            hintOverlay.animate()
                .alpha(0f)
                .setDuration(300)
                .withEndAction {
                    hintOverlay.visibility = View.GONE
                }
                .start()
        }

        autoStopped = false
        isStopping = false
        resetPhotoViewState()

        viewModel.incrementAttempt()
        statusText.text = "Logovanie..."
        viewModel.startLogging(requireActivity())
    }

    private fun stopCurrentLogging() {
        if (isStopping) return
        isStopping = true

        viewModel.stopLogging(requireActivity())
        resetPhotoViewState()

        photoView.isEnabled = false
        uploadOverlay.visibility = View.VISIBLE

        uploadCurrentLog {
            if (!isAdded) return@uploadCurrentLog

            uploadOverlay.visibility = View.GONE
            photoView.isEnabled = true
            isStopping = false

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
        stopButton.isEnabled = false
        UserSession.markCompleted(requireContext(), "zoom")
        successOverlay.visibility = View.VISIBLE

        successOverlay.findViewById<com.google.android.material.button.MaterialButton>(R.id.success_menu_button)
            .setOnClickListener {
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
            ?.filter { it.isFile && !it.name.contains("orientation", ignoreCase = true) }
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
