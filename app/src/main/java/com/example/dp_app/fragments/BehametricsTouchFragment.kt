package com.example.dp_app.fragments

import android.os.Bundle
import android.view.LayoutInflater
import android.view.View
import android.view.ViewGroup
import android.widget.Button
import android.widget.TextView
import android.widget.Toast
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
    private lateinit var directionText: TextView
    private lateinit var hintOverlay: View
    private lateinit var uploadOverlay: View
    private lateinit var viewPager: ViewPager2

    private val images = listOf(
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

    // Kolá 1-5 = DOPRAVA, kolá 6-10 = DOĽAVA
    private val totalRounds = 10
    private val rightRoundsCount = 5

    private var roundActive = false
    private var lastPage = 0

    private val pageChangeCallback = object : ViewPager2.OnPageChangeCallback() {
        override fun onPageSelected(position: Int) {
            if (!roundActive) return

            val currentRound = viewModel.currentAttempt.value ?: 0
            val isRightPhase = currentRound <= rightRoundsCount

            // Upozornenie pri swipe v zlom smere
            if (isRightPhase && position < lastPage) {
                Toast.makeText(requireContext(), "Pokračujte DOPRAVA →", Toast.LENGTH_SHORT).show()
            } else if (!isRightPhase && position > lastPage) {
                Toast.makeText(requireContext(), "← Pokračujte DOĽAVA", Toast.LENGTH_SHORT).show()
            }

            lastPage = position

            // Kolo je hotové keď sa dostane na koniec/začiatok
            val roundComplete = if (isRightPhase) {
                position == images.size - 1
            } else {
                position == 0
            }

            if (roundComplete) finishRound()
        }
    }

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
        directionText = view.findViewById(R.id.direction_text)
        hintOverlay = view.findViewById(R.id.hint_overlay)
        uploadOverlay = view.findViewById(R.id.upload_overlay)
        viewPager = view.findViewById(R.id.viewPager)

        viewModel.init(requireContext())
        viewPager.adapter = ImageAdapter(images)
        viewPager.registerOnPageChangeCallback(pageChangeCallback)

        viewModel.status.observe(viewLifecycleOwner) {
            statusText.text = it
        }

        viewModel.currentAttempt.observe(viewLifecycleOwner) { round ->
            counterText.text = "$round / $totalRounds"
            updateDirectionUI(round)
        }

        viewModel.isLogging.observe(viewLifecycleOwner) { logging ->
            val round = viewModel.currentAttempt.value ?: 0
            startButton.isEnabled = !logging && !roundActive && round < totalRounds
            stopButton.isEnabled = logging
        }

        startButton.setOnClickListener { startNextRound() }
        stopButton.setOnClickListener { finishRound() }

        backButton.setOnClickListener {
            findNavController().navigate(R.id.action_behametricsTouchFragment_to_introFragment)
        }

        backButton.visibility = View.GONE
        updateDirectionUI(0)
    }

    override fun onDestroyView() {
        super.onDestroyView()
        viewPager.unregisterOnPageChangeCallback(pageChangeCallback)
    }

    private fun startNextRound() {
        val round = viewModel.currentAttempt.value ?: 0
        if (round >= totalRounds) { finishAll(); return }

        if (round == 0) {
            hintOverlay.animate().alpha(0f).setDuration(300).withEndAction {
                hintOverlay.visibility = View.GONE
            }.start()
        }

        viewModel.incrementAttempt()
        val newRound = viewModel.currentAttempt.value ?: 0
        roundActive = true

        // Nastav ViewPager na štartovaciu pozíciu pre daný smer
        val isRightPhase = newRound <= rightRoundsCount
        if (isRightPhase) {
            viewPager.setCurrentItem(0, false)
            lastPage = 0
        } else {
            viewPager.setCurrentItem(images.size - 1, false)
            lastPage = images.size - 1
        }

        statusText.text = "Prebieha záznam..."
        viewModel.startLogging(requireActivity())
    }

    private fun finishRound() {
        if (!roundActive) return
        roundActive = false
        viewModel.stopLogging(requireActivity())

        val round = viewModel.currentAttempt.value ?: 0
        val direction = if (round <= rightRoundsCount) "doprava" else "dolava"

        uploadOverlay.visibility = View.VISIBLE
        uploadCurrentLog(direction) {
            uploadOverlay.visibility = View.GONE
            if (round >= totalRounds) {
                finishAll()
            } else {
                statusText.text = "Kolo $round dokončené. Pokračujte stlačením tlačidla."
                startButton.isEnabled = true
            }
        }
    }

    private fun finishAll() {
        statusText.text = "Všetky kolá boli úspešne dokončené."
        directionText.text = ""
        backButton.visibility = View.VISIBLE
        startButton.isEnabled = false
        stopButton.isEnabled = false
    }

    private fun updateDirectionUI(round: Int) {
        val nextRound = round + 1
        if (nextRound > totalRounds) return

        val isNextRight = nextRound <= rightRoundsCount
        if (isNextRight) {
            directionText.text = "→  DOPRAVA"
            startButton.text = "Spustiť kolo $nextRound  →"
        } else {
            directionText.text = "←  DOĽAVA"
            startButton.text = "←  Spustiť kolo $nextRound"
        }
    }

    private fun uploadCurrentLog(direction: String, onComplete: () -> Unit) {
        val logDir = File(requireContext().filesDir, "logs")

        if (!logDir.exists()) {
            onComplete()
            return
        }

        val files = logDir.listFiles()
            ?.filter { !it.name.contains("orientation", ignoreCase = true) }
            ?: emptyList()

        if (files.isEmpty()) {
            onComplete()
            return
        }

        val round = viewModel.currentAttempt.value ?: 0
        var uploaded = 0

        for (file in files) {
            val userId = UserSession.userId
            val filename = "kolo${round}_${direction}_${file.name}"
            val ref = FirebaseStorage.getInstance().reference
                .child("touch_gallery_behametrics/$direction/$userId/$filename")

            ref.putFile(Uri.fromFile(file))
                .addOnSuccessListener {
                    file.writeText("")
                    uploaded++
                    if (uploaded == files.size) onComplete()
                }
                .addOnFailureListener {
                    statusText.text = "Chyba: ${it.message}"
                    uploaded++
                    if (uploaded == files.size) onComplete()
                }
        }
    }
}
