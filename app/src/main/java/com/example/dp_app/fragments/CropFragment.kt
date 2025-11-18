package com.example.dp_app.fragments

import android.os.Bundle
import android.view.LayoutInflater
import android.view.View
import android.view.ViewGroup
import androidx.fragment.app.Fragment
import com.example.dp_app.R
import com.github.chrisbanes.photoview.PhotoView

class CropFragment : Fragment() {

    private lateinit var photoView: PhotoView

    override fun onCreateView(
        inflater: LayoutInflater,
        container: ViewGroup?,
        savedInstanceState: Bundle?
    ): View? {
        val view = inflater.inflate(R.layout.fragment_crop, container, false)

        photoView = view.findViewById(R.id.photoView)

        photoView.setImageResource(R.drawable.stvorec_zoom)

        photoView.viewTreeObserver.addOnGlobalLayoutListener {
            val drawable = photoView.drawable ?: return@addOnGlobalLayoutListener

            val imageWidth = drawable.intrinsicWidth.toFloat()
            val imageHeight = drawable.intrinsicHeight.toFloat()

            val frameSize = 350 * resources.displayMetrics.density

            val scaleX = frameSize / imageWidth
            val scaleY = frameSize / imageHeight

            val maxScale = maxOf(scaleX, scaleY)

            photoView.minimumScale = 1f
            photoView.maximumScale = maxScale

            // 🔥 POMALÝ zoom od začiatku do konca
            photoView.setScaleLevels(
                1.0f,    // minimum
                1.005f,    // pomalý stredný scale
                maxScale // maximum
            )
        }


        return view
    }
}


