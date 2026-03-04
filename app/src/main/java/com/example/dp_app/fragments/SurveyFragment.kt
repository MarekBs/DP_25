package com.example.dp_app.fragments

import android.os.Bundle
import android.view.LayoutInflater
import android.view.View
import android.view.ViewGroup
import android.widget.RadioButton
import android.widget.RadioGroup
import android.widget.Toast
import androidx.fragment.app.Fragment
import androidx.navigation.fragment.findNavController
import com.example.dp_app.R
import com.example.dp_app.UserSession
import com.google.android.material.button.MaterialButton
import com.google.android.material.textfield.TextInputEditText
import com.google.firebase.storage.FirebaseStorage

class SurveyFragment : Fragment() {

    private lateinit var genderGroup: RadioGroup
    private lateinit var ageInput: TextInputEditText
    private lateinit var submitButton: MaterialButton

    override fun onCreateView(
        inflater: LayoutInflater,
        container: ViewGroup?,
        savedInstanceState: Bundle?
    ): View {
        val view = inflater.inflate(R.layout.fragment_survey, container, false)

        genderGroup = view.findViewById(R.id.genderGroup)
        ageInput = view.findViewById(R.id.ageInput)
        submitButton = view.findViewById(R.id.submit_button)

        submitButton.setOnClickListener {
            val selectedGenderId = genderGroup.checkedRadioButtonId
            if (selectedGenderId == -1) {
                Toast.makeText(requireContext(), "Prosím vyberte pohlavie.", Toast.LENGTH_SHORT).show()
                return@setOnClickListener
            }

            val age = ageInput.text.toString().trim()
            if (age.isBlank()) {
                Toast.makeText(requireContext(), "Prosím zadajte vek.", Toast.LENGTH_SHORT).show()
                return@setOnClickListener
            }

            val gender = view.findViewById<RadioButton>(selectedGenderId).text.toString()
            submitButton.isEnabled = false
            uploadProfile(gender, age)
        }

        return view
    }

    private fun uploadProfile(gender: String, age: String) {
        val userId = UserSession.userId
        val content = "ID: $userId\nPohlavie: $gender\nVek: $age"
        val ref = FirebaseStorage.getInstance()
            .reference.child("user_profiles/$userId/profile.txt")

        ref.putBytes(content.toByteArray())
            .addOnSuccessListener {
                findNavController().navigate(R.id.action_surveyFragment_to_introFragment)
            }
            .addOnFailureListener {
                submitButton.isEnabled = true
                Toast.makeText(requireContext(), "Chyba pri ukladaní: ${it.message}", Toast.LENGTH_SHORT).show()
            }
    }
}
