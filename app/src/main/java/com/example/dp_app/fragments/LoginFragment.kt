package com.example.dp_app.fragments

import android.os.Bundle
import android.view.LayoutInflater
import android.view.View
import android.view.ViewGroup
import android.widget.Button
import android.widget.EditText
import android.widget.Toast
import androidx.fragment.app.Fragment
import androidx.navigation.fragment.findNavController
import com.example.dp_app.R
import com.example.dp_app.UserSession

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
            

            UserSession.userId = userId
            

            findNavController().navigate(R.id.action_loginFragment_to_introFragment)
        }

        return view
    }
}
