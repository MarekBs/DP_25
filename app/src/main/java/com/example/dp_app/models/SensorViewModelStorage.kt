package com.example.dp_app

import android.content.ContentValues
import android.content.Context
import android.hardware.Sensor
import android.hardware.SensorEvent
import android.hardware.SensorEventListener
import android.hardware.SensorManager
import android.media.AudioManager
import android.media.ToneGenerator
import android.net.Uri
import android.os.*
import android.provider.MediaStore
import android.util.Log
import androidx.annotation.RequiresApi
import androidx.lifecycle.ViewModel
import java.io.File
import java.io.FileWriter

class SensorViewModelStorage : ViewModel(), SensorEventListener {

    private var context: Context? = null
    private var sensorManager: SensorManager? = null
    private var fileWriter: FileWriter? = null
    private lateinit var tempFile: File

    private var tone: ToneGenerator? = null

    var isLogging = false
    private var index = 0
    private var lastLogTime = 0L
    private val samplingInterval = 20L // 20 ms = 50 Hz

    private var attitude = FloatArray(3)
    private var gravity = FloatArray(3)
    private var gyro = FloatArray(3)
    private var linearAcc = FloatArray(3)

    fun init(context: Context) {
        this.context = context.applicationContext
        this.sensorManager = context.getSystemService(Context.SENSOR_SERVICE) as SensorManager
        tone = ToneGenerator(AudioManager.STREAM_NOTIFICATION, 100)
    }

    @RequiresApi(Build.VERSION_CODES.Q)
    fun startLogging(onStart: (String) -> Unit, onStop: (String) -> Unit) {
        if (isLogging || context == null || sensorManager == null) return
        isLogging = true
        index = 0
        lastLogTime = 0L

        // Registrácia senzorov (50 Hz)
        val delayUs = 20_000
        sensorManager!!.getDefaultSensor(Sensor.TYPE_ROTATION_VECTOR)?.also {
            sensorManager!!.registerListener(this, it, delayUs)
        }
        sensorManager!!.getDefaultSensor(Sensor.TYPE_GRAVITY)?.also {
            sensorManager!!.registerListener(this, it, delayUs)
        }
        sensorManager!!.getDefaultSensor(Sensor.TYPE_GYROSCOPE)?.also {
            sensorManager!!.registerListener(this, it, delayUs)
        }
        sensorManager!!.getDefaultSensor(Sensor.TYPE_LINEAR_ACCELERATION)?.also {
            sensorManager!!.registerListener(this, it, delayUs)
        }

        // Dočasný súbor
        val logsDir = File(context!!.getExternalFilesDir(Environment.DIRECTORY_DOCUMENTS), "DP_logs")
        if (!logsDir.exists()) logsDir.mkdirs()
        tempFile = File(logsDir, "motion_log.csv")

        fileWriter = FileWriter(tempFile)
        fileWriter!!.append(
            "index\tattitude.roll\tattitude.pitch\tattitude.yaw\t" +
                    "gravity.x\tgravity.y\tgravity.z\t" +
                    "rotationRate.x\trotationRate.y\trotationRate.z\t" +
                    "userAcceleration.x\tuserAcceleration.y\tuserAcceleration.z\n"
        )

        // 🔔 1. Krátke pípnutie (priprava)
        tone?.startTone(ToneGenerator.TONE_PROP_BEEP, 300)

        // 🕒 Po 1 sekunde spusti skutočné logovanie
        Handler(Looper.getMainLooper()).postDelayed({
            onStart(tempFile.absolutePath)
            tone?.startTone(ToneGenerator.TONE_PROP_ACK, 300) // 🔔 začiatok logovania
            Log.d("SENSOR_LOG", "Started logging to: ${tempFile.absolutePath}")

            // ⏱️ Automatické zastavenie po 45 sekundách
            Handler(Looper.getMainLooper()).postDelayed({
                stopLogging(onStop)
                tone?.startTone(ToneGenerator.TONE_PROP_NACK, 400) // 🔔 koniec logovania
            }, 45_000)

        }, 1_000) // čakaj 1 sekundu pred štartom
    }

    @RequiresApi(Build.VERSION_CODES.Q)
    fun stopLogging(onStop: (String) -> Unit) {
        if (!isLogging) return
        isLogging = false
        sensorManager?.unregisterListener(this)

        try {
            fileWriter?.flush()
            fileWriter?.close()
            val destPath = saveCsvToDownloads(tempFile)
            onStop(destPath)
        } catch (e: Exception) {
            Log.e("SENSOR_LOG", "Error saving file", e)
            onStop("⚠️ Error saving file: ${e.message}")
        }
    }

    @RequiresApi(Build.VERSION_CODES.Q)
    private fun saveCsvToDownloads(sourceFile: File): String {
        val resolver = context!!.contentResolver
        val fileName = "motion_log_${System.currentTimeMillis()}.csv"

        val contentValues = ContentValues().apply {
            put(MediaStore.Downloads.DISPLAY_NAME, fileName)
            put(MediaStore.Downloads.MIME_TYPE, "text/csv")
            put(MediaStore.Downloads.RELATIVE_PATH, "Download/DP_logs")
            put(MediaStore.Downloads.IS_PENDING, 1)
        }

        val uri: Uri? = resolver.insert(MediaStore.Downloads.EXTERNAL_CONTENT_URI, contentValues)
        var savedPath = "Unknown"
        uri?.let {
            resolver.openOutputStream(it)?.use { outputStream ->
                sourceFile.inputStream().use { input ->
                    input.copyTo(outputStream)
                }
            }
            contentValues.clear()
            contentValues.put(MediaStore.Downloads.IS_PENDING, 0)
            resolver.update(it, contentValues, null, null)
            savedPath = "Downloads/DP_logs/$fileName"
        }
        return savedPath
    }

    override fun onSensorChanged(event: SensorEvent) {
        if (!isLogging || fileWriter == null) return

        val now = SystemClock.elapsedRealtime()
        if (now - lastLogTime < samplingInterval) return
        lastLogTime = now

        when (event.sensor.type) {
            Sensor.TYPE_ROTATION_VECTOR -> {
                val rotMatrix = FloatArray(9)
                val orientationVals = FloatArray(3)
                try {
                    SensorManager.getRotationMatrixFromVector(rotMatrix, event.values)
                    SensorManager.getOrientation(rotMatrix, orientationVals)
                    attitude = orientationVals.copyOf()
                } catch (_: Exception) {}
            }
            Sensor.TYPE_GRAVITY -> {
                val v = event.values
                gravity[0] = v[0]
                gravity[1] = -v[1]
                gravity[2] = -v[2]
            }
            Sensor.TYPE_GYROSCOPE -> {
                val v = event.values
                gyro[0] = v[0]
                gyro[1] = -v[1]
                gyro[2] = -v[2]
            }
            Sensor.TYPE_LINEAR_ACCELERATION -> {
                val v = event.values
                linearAcc[0] = v[0]
                linearAcc[1] = -v[1]
                linearAcc[2] = -v[2]
            }
        }

        val safe = { v: Float -> if (v.isNaN() || v.isInfinite()) 0f else v }

        try {
            val line = String.format(
                "%d\t%.6f\t%.6f\t%.6f\t%.6f\t%.6f\t%.6f\t%.6f\t%.6f\t%.6f\t%.6f\t%.6f\t%.6f\n",
                index,
                safe(attitude[2]), safe(attitude[1]), safe(attitude[0]),
                safe(gravity[0]), safe(gravity[1]), safe(gravity[2]),
                safe(gyro[0]), safe(gyro[1]), safe(gyro[2]),
                safe(linearAcc[0]), safe(linearAcc[1]), safe(linearAcc[2])
            )
            fileWriter!!.append(line)
            if (index % 10 == 0) fileWriter!!.flush()
            index++
        } catch (e: Exception) {
            Log.e("SENSOR_LOG", "Write failed", e)
        }
    }

    override fun onAccuracyChanged(sensor: Sensor?, accuracy: Int) {}
}

