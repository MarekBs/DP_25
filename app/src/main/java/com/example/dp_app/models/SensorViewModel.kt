package com.example.dp_app.models

import android.content.Context
import android.hardware.*
import android.media.AudioManager
import android.media.ToneGenerator
import android.net.Uri
import android.os.Handler
import android.os.Looper
import android.os.SystemClock
import android.util.Log
import androidx.lifecycle.LiveData
import androidx.lifecycle.MutableLiveData
import androidx.lifecycle.ViewModel
import com.example.dp_app.UserSession
import com.google.firebase.storage.FirebaseStorage
import java.io.File
import java.io.FileWriter

class SensorViewModel : ViewModel(), SensorEventListener {

    private var sensorManager: SensorManager? = null
    private var context: Context? = null
    private var tone: ToneGenerator? = null
    private var fileWriter: FileWriter? = null

    private lateinit var currentFile: File
    var desiredFilename: String = ""

    private val _status = MutableLiveData("Čakanie na spustenie...")
    val status: LiveData<String> get() = _status

    private val _isLogging = MutableLiveData(false)
    val isLogging: LiveData<Boolean> get() = _isLogging

    private val _isUploading = MutableLiveData(false)
    val isUploading: LiveData<Boolean> get() = _isUploading

    private val _currentAttempt = MutableLiveData(0)
    val currentAttempt: LiveData<Int> get() = _currentAttempt

    val maxAttempts = 15

    private var lastLogTime = 0L
    private val samplingInterval = 20L // 50 Hz

    private var isAttitudeInitialized = false

    private var attitude = FloatArray(3)
    private var gravity = FloatArray(3)
    private var gyro = FloatArray(3)
    private var linearAcc = FloatArray(3)
    var index = 0


    fun init(context: Context) {
        this.context = context.applicationContext
        sensorManager = context.getSystemService(Context.SENSOR_SERVICE) as SensorManager
        tone = ToneGenerator(AudioManager.STREAM_NOTIFICATION, 100)
    }

    fun incrementAttempt() {
        _currentAttempt.value = (_currentAttempt.value ?: 0) + 1
    }

    fun startLogging() {
        if (_isLogging.value == true) return
        if (sensorManager == null || context == null) return

        _status.value = "Spúšťanie..."
        tone?.startTone(ToneGenerator.TONE_PROP_BEEP, 300)

        Handler(Looper.getMainLooper()).postDelayed({

            _isLogging.value = true
            _status.value = "Nahrávanie..."
            isAttitudeInitialized = false
            index = 0
            lastLogTime = 0L

            val logsDir = File(context!!.filesDir, "logs")
            if (!logsDir.exists()) logsDir.mkdirs()

            val fileName = if (desiredFilename.isNotBlank()) {
                "${desiredFilename}.csv"
            } else {
                "motion_${System.currentTimeMillis()}.csv"
            }

            currentFile = File(logsDir, fileName)
            fileWriter = FileWriter(currentFile)

            fileWriter!!.append(
                "index\t" +
                        "attitude.roll\tattitude.pitch\tattitude.yaw\t" +
                        "gravity.x\tgravity.y\tgravity.z\t" +
                        "rotationRate.x\trotationRate.y\trotationRate.z\t" +
                        "userAcceleration.x\tuserAcceleration.y\tuserAcceleration.z\n"
            )

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

            tone?.startTone(ToneGenerator.TONE_PROP_ACK, 300)

        }, 1000)
    }


    fun stopLogging() {

        if (_isLogging.value != true) return

        _isLogging.value = false
        _status.value = "Zastavovanie..."

        sensorManager?.unregisterListener(this)

        try {
            fileWriter?.flush()
            fileWriter?.close()
        } catch (e: Exception) {
            Log.e("SENSOR_LOG", "File close error", e)
        }

        tone?.startTone(ToneGenerator.TONE_PROP_NACK, 300)

        _status.value = "⬆ Nahrávanie na server..."
        _isUploading.postValue(true)

        uploadToFirebase(currentFile) {
            _isUploading.postValue(false)
            _status.postValue("Súbory nahrané ✅")
        }
    }


    private fun uploadToFirebase(file: File, onComplete: () -> Unit) {
        val storage = FirebaseStorage.getInstance()
        val uri = Uri.fromFile(file)
        val userId = UserSession.userId
        val ref = storage.reference.child("logs_motionsense/$userId/${file.name}")

        ref.putFile(uri)
            .addOnSuccessListener {
                file.delete()
                onComplete() }
            .addOnFailureListener {
                _status.value = "Nahrávanie zlyhalo ❌"
                onComplete()
            }
    }


    override fun onSensorChanged(event: SensorEvent) {
        if (_isLogging.value != true) return
        if (fileWriter == null) return

        when (event.sensor.type) {

            Sensor.TYPE_ROTATION_VECTOR -> {
                val rotMatrix = FloatArray(9)
                val orientationVals = FloatArray(3)

                SensorManager.getRotationMatrixFromVector(rotMatrix, event.values)
                SensorManager.getOrientation(rotMatrix, orientationVals)
                attitude = orientationVals.copyOf()

                if (!isAttitudeInitialized) isAttitudeInitialized = true
            }

            Sensor.TYPE_GRAVITY -> {
                val v = event.values
                gravity[0] = v[0] / 9.81f
                gravity[1] = v[1] / 9.81f
                gravity[2] = v[2] / 9.81f
            }

            Sensor.TYPE_GYROSCOPE -> {
                val v = event.values
                gyro[0] = v[0]
                gyro[1] = v[1]
                gyro[2] = v[2]
            }

            Sensor.TYPE_LINEAR_ACCELERATION -> {

                if (!isAttitudeInitialized) return

                val now = SystemClock.elapsedRealtime()
                if (now - lastLogTime < samplingInterval) return
                lastLogTime = now

                val v = event.values
                linearAcc[0] = v[0] / 9.81f
                linearAcc[1] = v[1] / 9.81f
                linearAcc[2] = v[2] / 9.81f

                try {
                    val line =
                        "${index}\t${attitude[2]}\t${attitude[1]}\t${attitude[0]}\t" +
                                "${gravity[0]}\t${gravity[1]}\t${gravity[2]}\t" +
                                "${gyro[0]}\t${gyro[1]}\t${gyro[2]}\t" +
                                "${linearAcc[0]}\t${linearAcc[1]}\t${linearAcc[2]}\n"

                    fileWriter!!.append(line)
                    if (index % 200 == 0) fileWriter!!.flush()

                    index++

                } catch (e: Exception) {
                    Log.e("SENSOR_LOG", "Write failed", e)
                }
            }
        }
    }

    override fun onAccuracyChanged(sensor: Sensor?, accuracy: Int) {}

    override fun onCleared() {
        stopLogging()
        super.onCleared()
    }
}
