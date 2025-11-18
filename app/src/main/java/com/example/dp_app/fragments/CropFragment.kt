package com.example.dp_app.fragments

import android.os.Bundle
import android.view.LayoutInflater
import android.view.View
import android.view.ViewGroup
import android.widget.Button
import android.widget.EditText
import android.widget.TextView
import androidx.fragment.app.Fragment
import androidx.fragment.app.viewModels
import com.example.dp_app.R
import com.example.dp_app.BehametricsViewModel
import com.github.chrisbanes.photoview.PhotoView
import com.google.firebase.storage.FirebaseStorage

import android.net.Uri
import androidx.appcompat.app.AppCompatActivity
import java.io.File

class CropFragment : Fragment() {

    private val viewModel: BehametricsViewModel by viewModels()

    private lateinit var photoView: PhotoView
    private lateinit var statusText: TextView
    private lateinit var startButton: Button
    private lateinit var stopButton: Button
    private lateinit var idInput: EditText

    override fun onCreateView(
        inflater: LayoutInflater,
        container: ViewGroup?,
        savedInstanceState: Bundle?
    ): View {
        return inflater.inflate(R.layout.fragment_crop, container, false)
    }

    override fun onViewCreated(view: View, savedInstanceState: Bundle?) {
        super.onViewCreated(view, savedInstanceState)

        // Nastav obrázok
        photoView = view.findViewById(R.id.photoView)
        photoView.setImageResource(R.drawable.stvorec_zoom)

        // Získaj rozmery obrázka priamo z drawable
        val drawable = resources.getDrawable(R.drawable.stvorec_zoom, null)
        val imageWidth = drawable.intrinsicWidth.toFloat()
        val imageHeight = drawable.intrinsicHeight.toFloat()

        // Veľkosť rámčeka (350dp)
        val frameSize = 350 * resources.displayMetrics.density

        val scaleX = frameSize / imageWidth
        val scaleY = frameSize / imageHeight
        val maxScale = maxOf(scaleX, scaleY)

        // Nastav zoom úrovne
        photoView.minimumScale = 1f
        photoView.maximumScale = maxScale

        photoView.setScaleLevels(
            1.0f,
            1.005f,
            maxScale
        )


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
    }

    private fun uploadTouchLogs() {
        val logDir = File(requireContext().filesDir, "logs")
        val id = idInput.text.toString()

        if (!logDir.exists()) {
            statusText.text = "❗ Logs folder not found."
            return
        }

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

    private fun uploadToFirebaseTouch(file: File, id: String, onFinish: () -> Unit) {
        val storage = FirebaseStorage.getInstance()
        val uri = Uri.fromFile(file)

        val filename = "${id}_${file.name}"
        val ref = storage.reference.child("touch_zoom_behametrics/$filename")

        ref.putFile(uri)
            .addOnSuccessListener {
                file.writeText("") // flush
                onFinish()
            }
            .addOnFailureListener {
                statusText.text = "Upload failed: ${it.message}"
                onFinish()
            }
    }
}


