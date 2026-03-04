package com.example.dp_app

import android.content.Context

object UserSession {
    var userId: String = ""

    fun isLoggedIn(): Boolean = userId.isNotBlank()

    fun clear() {
        userId = ""
    }

    fun markCompleted(context: Context, scenario: String) {
        val prefs = context.getSharedPreferences("completed_$userId", Context.MODE_PRIVATE)
        prefs.edit().putBoolean(scenario, true).apply()
    }

    fun isCompleted(context: Context, scenario: String): Boolean {
        val prefs = context.getSharedPreferences("completed_$userId", Context.MODE_PRIVATE)
        return prefs.getBoolean(scenario, false)
    }
}
