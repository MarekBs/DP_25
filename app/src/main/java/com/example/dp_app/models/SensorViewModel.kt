package com.example.dp_app

import android.content.Context
import android.hardware.Sensor
import android.hardware.SensorEvent
import android.hardware.SensorEventListener
import android.hardware.SensorManager
import android.media.AudioManager
import android.media.ToneGenerator
import android.net.Uri
import android.os.Handler
import android.os.Looper
import android.os.SystemClock
import android.util.Log
import androidx.lifecycle.ViewModel
import com.google.firebase.storage.FirebaseStorage
import java.io.File
import java.io.FileWriter

class SensorViewModel : ViewModel(), SensorEventListener {

    private var fileWriter: FileWriter? = null
    private var sensorManager: SensorManager? = null
    private var context: Context? = null
    private var tone: ToneGenerator? = null

    var isLogging = false
    var index = 0
    var lastLogTime = 0L
    private val samplingInterval = 20L // 20 ms = 50 Hz

    private var attitude = FloatArray(3)
    private var gravity = FloatArray(3)
    private var gyro = FloatArray(3)
    private var linearAcc = FloatArray(3)
    private lateinit var currentFile: File

    fun init(context: Context) {
        this.context = context.applicationContext
        this.sensorManager = context.getSystemService(Context.SENSOR_SERVICE) as SensorManager
        this.tone = ToneGenerator(AudioManager.STREAM_NOTIFICATION, 100)
    }

    fun startLogging() {
        if (isLogging || context == null || sensorManager == null) return

        // 🔔 krátke pípnutie pred štartom
        tone?.startTone(ToneGenerator.TONE_PROP_BEEP, 300)
        Log.d("SENSOR_LOG", "Beep - preparing to log in 1 second...")

        Handler(Looper.getMainLooper()).postDelayed({
            isLogging = true
            index = 0
            lastLogTime = 0L

            val delayUs = 20_000 // 50 Hz

            // Registrácia senzorov
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

            // 🔹 Príprava logovacieho súboru
            val logsDir = File(context!!.filesDir, "logs")
            if (!logsDir.exists()) logsDir.mkdirs()
            currentFile = File(logsDir, "motion_log_${System.currentTimeMillis()}.csv")

            fileWriter = FileWriter(currentFile)
            fileWriter!!.append(
                "index\tattitude.roll\tattitude.pitch\tattitude.yaw\t" +
                        "gravity.x\tgravity.y\tgravity.z\t" +
                        "rotationRate.x\trotationRate.y\trotationRate.z\t" +
                        "userAcceleration.x\tuserAcceleration.y\tuserAcceleration.z\n"
            )

            // 🔔 začiatok logovania
            tone?.startTone(ToneGenerator.TONE_PROP_ACK, 300)
            Log.d("SENSOR_LOG", "Started logging to: ${currentFile.absolutePath}")

            // automatické zastavenie po 45 sekundách
            Handler(Looper.getMainLooper()).postDelayed({
                stopLogging()
            }, 45_000)
        }, 1_000)
    }

    fun stopLogging() {
        if (!isLogging) return
        isLogging = false

        sensorManager?.unregisterListener(this)

        try {
            fileWriter?.flush()
            fileWriter?.close()
            Log.d("SENSOR_LOG", "Stopped logging.")
            tone?.startTone(ToneGenerator.TONE_PROP_NACK, 400)

            // 🔼 Upload na Firebase Storage
            uploadToFirebase(currentFile)

        } catch (e: Exception) {
            Log.e("SENSOR_LOG", "Error closing file", e)
        }
    }

    private fun uploadToFirebase(file: File) {
        try {
            val storage = FirebaseStorage.getInstance()
            val fileUri = Uri.fromFile(file)
            val fileRef = storage.reference.child("logs/${file.name}")

            val uploadTask = fileRef.putFile(fileUri)
            uploadTask.addOnSuccessListener {
                fileRef.downloadUrl.addOnSuccessListener { uri ->
                    Log.d("FIREBASE_UPLOAD", "✅ File uploaded successfully: $uri")
                }
            }.addOnFailureListener { e ->
                Log.e("FIREBASE_UPLOAD", "❌ Upload failed: ${e.message}")
            }

        } catch (e: Exception) {
            Log.e("FIREBASE_UPLOAD", "❌ Exception: ${e.message}")
        }
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
                gravity[0] = v[0] / 9.81f
                gravity[1] = -v[1] / 9.81f
                gravity[2] = -v[2] / 9.81f
            }
            Sensor.TYPE_GYROSCOPE -> {
                val v = event.values
                gyro[0] = v[0]
                gyro[1] = -v[1]
                gyro[2] = -v[2]
            }
            Sensor.TYPE_LINEAR_ACCELERATION -> {
                val v = event.values
                linearAcc[0] = v[0] / 9.81f
                linearAcc[1] = -v[1] / 9.81f
                linearAcc[2] = -v[2] / 9.81f
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

    override fun onCleared() {
        stopLogging()
        super.onCleared()
    }
}



