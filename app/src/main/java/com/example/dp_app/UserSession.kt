package com.example.dp_app


object UserSession {
    var userId: String = ""
    
    fun isLoggedIn(): Boolean = userId.isNotBlank()
    
    fun clear() {
        userId = ""
    }
}
