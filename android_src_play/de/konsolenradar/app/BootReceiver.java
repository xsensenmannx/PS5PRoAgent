package de.konsolenradar.app;

import android.content.BroadcastReceiver;
import android.content.Context;
import android.content.Intent;
import android.util.Log;

import org.json.JSONObject;

import java.io.ByteArrayOutputStream;
import java.io.File;
import java.io.FileInputStream;

/**
 * Startet den Foreground-Service nach Neustart oder App-Update, aber nur wenn
 * der Nutzer AUTO in der App aktiviert hat. Play-Variante mit neutraler Marke.
 */
public class BootReceiver extends BroadcastReceiver {
    private static final String TAG = "KonsolenRadarBoot";
    private static final String SETTINGS = "ps5pro_settings.json";
    private static final int MIN_INTERVALL = 900;

    @Override
    public void onReceive(Context context, Intent intent) {
        if (context == null || intent == null) return;
        String action = intent.getAction();
        if (!Intent.ACTION_BOOT_COMPLETED.equals(action)
                && !Intent.ACTION_MY_PACKAGE_REPLACED.equals(action)) {
            return;
        }

        try {
            File dir = context.getFilesDir();
            if (dir == null) return;
            File settingsFile = new File(dir, SETTINGS);
            if (!settingsFile.exists()) {
                Log.i(TAG, "keine Einstellungen - AUTO wurde nie aktiviert");
                return;
            }

            JSONObject settings = new JSONObject(readUtf8(settingsFile));
            if (!settings.optBoolean("auto_scan", false)) {
                Log.i(TAG, "AUTO ist aus - Service bleibt aus");
                return;
            }

            int interval = settings.optInt("auto_interval", MIN_INTERVALL);
            if (interval < MIN_INTERVALL) interval = MIN_INTERVALL;

            JSONObject argument = new JSONObject();
            argument.put("interval", interval);
            argument.put("data_dir", dir.getAbsolutePath());
            argument.put("brand", "play");

            ServicePs5proscan.start(
                    context,
                    "notify_icon",
                    "Konsolen-Radar",
                    "Prueft Haendler im Hintergrund",
                    argument.toString());
            Log.i(TAG, "Hintergrund-Service nach " + action + " gestartet");
        } catch (Throwable t) {
            Log.e(TAG, "Service-Start nach Boot fehlgeschlagen", t);
        }
    }

    private static String readUtf8(File file) throws Exception {
        FileInputStream in = new FileInputStream(file);
        try {
            ByteArrayOutputStream out = new ByteArrayOutputStream();
            byte[] buffer = new byte[4096];
            int n;
            while ((n = in.read(buffer)) > 0) out.write(buffer, 0, n);
            return out.toString("UTF-8");
        } finally {
            in.close();
        }
    }
}
