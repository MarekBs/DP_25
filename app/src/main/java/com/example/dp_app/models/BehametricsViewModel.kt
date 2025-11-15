package com.example.dp_app

import android.app.Activity
import android.content.Context
import androidx.lifecycle.LiveData
import androidx.lifecycle.MutableLiveData
import androidx.lifecycle.ViewModel
import com.behametrics.logger.Logger
import java.io.File

class BehametricsViewModel : ViewModel() {

    private val _status = MutableLiveData("Idle")
    val status: LiveData<String> = _status

    private val _isLogging = MutableLiveData(false)
    val isLogging: LiveData<Boolean> = _isLogging

    private lateinit var logDir: File

    fun init(context: Context) {
        // správny priečinok: /data/.../files/logs
        logDir = File(context.filesDir, "logs")
        if (!logDir.exists()) logDir.mkdirs()
    }

    fun startLogging(activity: Activity) {
        try {
            Logger.start(activity)
            _isLogging.value = true
            _status.value = "Logging started"
        } catch (e: Exception) {
            _status.value = "Error: ${e.message}"
        }
    }

    fun stopLogging(activity: Activity) {
        try {
            Logger.stop(activity)
            _isLogging.value = false
            _status.value = "Logging stopped"
        } catch (e: Exception) {
            _status.value = "Error: ${e.message}"
        }
    }

    fun getLogFiles(): List<File> {
        return logDir.listFiles()?.toList() ?: emptyList()
    }

    fun setStatus(text: String) {
        _status.value = text
    }
}

