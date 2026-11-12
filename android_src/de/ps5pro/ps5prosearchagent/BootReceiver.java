package de.ps5pro.ps5prosearchagent;

import android.content.BroadcastReceiver;
import android.content.Context;
import android.content.Intent;
import android.util.Log;

import org.json.JSONObject;

import java.io.ByteArrayOutputStream;
import java.io.File;
import java.io.FileInputStream;

/**
 * Startet den bereits vorhandenen Foreground-Service nach einem Neustart oder
 * App-Update - aber nur, wenn der Nutzer AUTO in der App aktiviert hat.
 *
 * Der Receiver ist absichtlich nicht directBootAware: ps5pro_settings.json
 * liegt im credential-encrypted files-Verzeichnis und ist vor dem ersten
 * Entsperren nicht lesbar. Android liefert ACTION_BOOT_COMPLETED deshalb erst
 * nach dem Entsperren; das ist fuer diesen Preis-Beobachter ausreichend.
 */
public class BootReceiver extends BroadcastReceiver {
    private static final String TAG = "PS5ProBoot";
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

            // specialUse ist auf Android 15 von der BOOT_COMPLETED-Sperre
            // ausgenommen (dataSync waere hier z. B. nicht erlaubt).
            ServicePs5proscan.start(
                    context,
                    "notify_icon",
                    "PS5 Pro Scan",
                    "Prueft Haendler im Hintergrund",
                    argument.toString());
            Log.i(TAG, "Hintergrund-Service nach " + action + " gestartet");
        } catch (Throwable t) {
            // Ein fehlender Start darf den Boot nicht verhindern; der Nutzer
            // kann AUTO jederzeit in der App erneut aktivieren.
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
