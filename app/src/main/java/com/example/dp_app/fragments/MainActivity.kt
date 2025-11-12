package com.example.dp_app.fragments

import android.os.Bundle
import androidx.appcompat.app.AppCompatActivity
import com.example.dp_app.R
import com.example.dp_app.SensorFragment
import com.example.dp_app.SensorFragmentStorage

class MainActivity : AppCompatActivity() {
    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        setContentView(R.layout.activity_main)

        // Načítame fragment do activity
        if (savedInstanceState == null) {
            supportFragmentManager.beginTransaction()
                .replace(R.id.fragment_container, SensorFragmentStorage())
                .commit()
        }
    }
}