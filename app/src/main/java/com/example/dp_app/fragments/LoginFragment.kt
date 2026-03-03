package com.example.dp_app.fragments

import android.os.Bundle
import android.view.LayoutInflater
import android.view.View
import android.view.ViewGroup
import android.widget.Button
import android.widget.EditText
import android.widget.Toast
import androidx.appcompat.app.AlertDialog
import androidx.fragment.app.Fragment
import androidx.navigation.fragment.findNavController
import com.example.dp_app.R
import com.example.dp_app.UserSession
import com.google.firebase.storage.FirebaseStorage
import com.google.firebase.storage.StorageException

class LoginFragment : Fragment() {

    private lateinit var idInput: EditText
    private lateinit var loginButton: Button

    override fun onCreateView(
        inflater: LayoutInflater,
        container: ViewGroup?,
        savedInstanceState: Bundle?
    ): View {
        val view = inflater.inflate(R.layout.fragment_login, container, false)

        idInput = view.findViewById(R.id.idInput)
        loginButton = view.findViewById(R.id.login_button)

        loginButton.setOnClickListener {
            val userId = idInput.text.toString().trim()

            if (userId.isBlank()) {
                Toast.makeText(requireContext(), "Prosím zadajte vaše ID", Toast.LENGTH_SHORT).show()
                return@setOnClickListener
            }

            loginButton.isEnabled = false
            checkIfIdExists(userId)
        }

        return view
    }

    private fun checkIfIdExists(userId: String) {
        val markerRef = FirebaseStorage.getInstance()
            .reference.child("registered_users/$userId/marker.txt")

        markerRef.metadata
            .addOnSuccessListener {
                loginButton.isEnabled = true
                showConfirmDialog(userId)
            }
            .addOnFailureListener { exception ->
                loginButton.isEnabled = true
                val code = (exception as? StorageException)?.errorCode
                if (code == StorageException.ERROR_OBJECT_NOT_FOUND) {
                    createMarkerAndLogin(userId)
                } else {
                    Toast.makeText(requireContext(), "Chyba pripojenia: ${exception.message}", Toast.LENGTH_SHORT).show()
                }
            }
    }

    private fun showConfirmDialog(userId: String) {
        AlertDialog.Builder(requireContext())
            .setTitle("ID už existuje")
            .setMessage("Zadané ID už niekto používa. Naozaj sa chcete prihlásiť s týmto ID?")
            .setPositiveButton("Áno") { _, _ -> proceedLogin(userId) }
            .setNegativeButton("Nie", null)
            .show()
    }

    private fun createMarkerAndLogin(userId: String) {
        val markerRef = FirebaseStorage.getInstance()
            .reference.child("registered_users/$userId/marker.txt")

        markerRef.putBytes(userId.toByteArray())
            .addOnSuccessListener { proceedLogin(userId) }
            .addOnFailureListener { proceedLogin(userId) }
    }

    private fun proceedLogin(userId: String) {
        UserSession.userId = userId
        findNavController().navigate(R.id.action_loginFragment_to_introFragment)
    }
}
